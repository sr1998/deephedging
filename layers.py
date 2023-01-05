# -*- coding: utf-8 -*-
"""
Utility layers
--------------
June 30, 2022
@author: hansbuehler
"""

from .base import Logger, Config, tf, dh_dtype, tf_glorot_value, Int, Float # NOQA
from collections.abc import Mapping, Sequence # NOQA
import numpy as np
_log = Logger(__file__)

class VariableLayer(tf.keras.layers.Layer):
    """
    A variable layer.
    The variable can be initialized with a specific value, or with the standard Keras glorot initializer.
    """
    
    def __init__(self, init, trainable : bool = True, name : str = None, dtype : tf.DType = dh_dtype ):
        """
        Initialized the variable

        Args:
            init : 
                If a float, a numpy array, or a tensor, then this is the initial value of the variable
                If this is a tuple, a tensorshape, or a numpyshape then this will be the shape of the variable.
            trainable : bool
            name : str
            dtype : dtype
        """        
        tf.keras.layers.Layer.__init__(self, name=name, dtype=dtype )        
        if not isinstance(init, (float, np.ndarray, tf.Tensor)):
            _log.verify( isinstance(init, (tuple, tf.TensorShape)), "'init' must of type float, np.array, tf.Tensor, tuple, or tf.TensorShape. Found type %s", type(init))
            init              = tf_glorot_value(init)
        self.variable     = tf.Variable( init, trainable=trainable, name=name+"_variable" if not name is None else None, dtype=self.dtype )
        
    def call( self, dummy_data : dict = None, training : bool = False ) -> tf.Tensor:
        """ Return variable value """
        return self.variable

class DenseLayer(tf.keras.layers.Layer):
    """
    Core dense Keras layer
    Pretty generic dense layer. Also acts as plain variable if it does not depend on any variables.
    """
    
    def __init__(self, features, nOutput : int, initial_value = None, config : Config = Config(), name : str = None, dtype : tf.DType = dh_dtype ):
        """
        Create a simple dense later with nInput nodes and nOuput nodes.
        
        Parameters
        ----------
            features
                Input features. If None, then the layer will become a simple variable with nOutput nodes.
            nOutput : int
                Number of output nodes
            width : int = 20
            depth : int = 3
            activation : str = "relu"
            name : str, optional
                Name of the layer
            dtype : tf.DType, optional
                dtype
        """
        tf.keras.layers.Layer.__init__(self, name=name, dtype=dtype )
        self.nOutput           = int(nOutput)
        self.width             = config("width",20, Int>0, help="Network width.")
        self.activation        = config("activation","relu", help="Network activation function")
        self.depth             = config("depth", 3, Int>0, help="Network depth")
        self.final_activation  = config("final_activation","linear", help="Network activation function for the last layer")
        self.zero_model        = config("zero_model", False, bool, "Create a model with zero initial value, but randomized initial gradients")
        self.features          = sorted( set( features ) ) if not features is None else None
        self.features          = self.features if len(self.features) > 0 else None
        self.nFeatures         = None
        self.model             = None        
        self.initial_value     = None
        if not initial_value is None:
            if isinstance(initial_value, np.ndarray):
                _log.verify( initial_value.shape == (nOutput,), "Internal error: initial value shape %s does not match 'nOutput' of %ld", initial_value.shape, nOutput )
                self.initial_value = initial_value
            else:
                self.initial_value = np.full((nOutput,), initial_value)
                
        _log.verify( self.nOutput > 0, "'nOutput' must be positive; found %ld", self.nOutput )
        config.done()

    def build( self, shapes : dict ):
        """ 
        Keras layer builld() function.
        'shapes' must be a dictionary
        """
        _log.verify( self.features is None or isinstance(shapes, Mapping), "'shapes' must be a dictionary type if 'features' are specified. Found type %s", type(shapes ))
        assert self.nFeatures is None and self.model is None, ("build() called twice")
        
        # collect features
        self.nFeatures = 0
        if not self.features is None:
            for feature in self.features:
                _log.verify( feature in shapes, "Unknown feature '%s'. Known features are: %s. List of requested features: %s", feature, list(shapes), list(self.features) )
                fs = shapes[feature]
                assert len(fs) == 2, ("Internal error: all features should have been flattend. Found feature '%s' with shape %s" % (feature, fs))
                self.nFeatures += fs[1]
    
        # build model
        # simple feedforward model as an example
        if self.nFeatures == 0:
            """ Create model without inputs, but which is trainable.
                Same as creating a plain variable, but wrappong it allows us using
                a single self.model
            """
            self.model    = VariableLayer( (self.nOutput,) if self.initial_value is None else self.initial_value, trainable=True, name=self.name+"_variable_layer" if not self.name is None else None, dtype=self.dtype )
        else:
            """ Simple feed forward network with optional recurrent layer """
            inp = tf.keras.layers.Input( shape=(self.nFeatures,), dtype=self.dtype )
            x = inp
            x = tf.keras.layers.Dense( units=self.width,
                                       activation=self.activation,
                                       use_bias=True )(x)
                                               
            for d in range(self.depth-1):
                x = tf.keras.layers.Dense( units=self.width,
                                           activation=self.activation,
                                           use_bias=True )(x)
            x = tf.keras.layers.Dense(     units=self.nOutput,
                                           activation=self.final_activation,
                                           use_bias=True )(x)
            
            
            self.model         = tf.keras.Model( inputs=inp, outputs=x )
            
            if self.zero_model:
                raise NotImplementedError("zero_model")
                """
                cloned = tf.keras.clone_model( self.model, input_tensors=inp )
                assert len(cloned.weights) == len(self.model.weights), "Internal error: cloned model has differnet number of variables?"
                for mvar, cvar in zip( self.model.weights, cloned.weights):
                    cvar.set_weights(mvar.set_weights)
                cloned.trainable = False
                self.model = tf.keras.layers.
                """  
        
    def call( self, data : dict, training : bool = False ) -> tf.Tensor:
        """
        Ask the agent for an action.
    
        Parameters
        ----------
            data : dict
                Contains all available features at this time step.
                This must be a dictionary.
            training : bool, optional
                Whether we are training or not
                
        Returns
        -------
            Tensor with actions. The second dimension of
            the tensor corresponds to self.nInst
    
        """
        _log.verify( self.features is None or isinstance(data, Mapping), "'data' must be a dictionary type. Found type %s", type(data ))
        _log.verify( not self.model is None, "Model has not been buit yet")

        # simple variable --> return as such
        if self.nFeatures == 0:
            return self.model(data, training=training)
        
        # compile concatenated feature tensor
        features = [ data[_] for _ in self.features ]
        features = tf.concat( features, axis=1, name = "features" )      
        assert self.nFeatures == features.shape[1], ("Condig error: number of features should match up. Found %ld and %ld" % ( self.nFeatures, features.shape[1] ) )
        return self.model( features, training=training )
    