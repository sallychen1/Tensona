import numpy as np
import tensorflow as tf


class Atten_Head(tf.keras.layers.Layer):
	def __init__(self, input_size, output_size, use_mask):		
		super(Atten_Head, self).__init__()

		self.use_mask = use_mask

		# Initialize the weight matrices for K, V, and Q.
		# They should be able to multiply an input_size vector to produce an output_size vector 
		self.K = self.add_weight(shape=(input_size, output_size), initializer="random_normal", trainable=True)
		self.V = self.add_weight(shape=(input_size, output_size), initializer="random_normal", trainable=True)
		self.Q = self.add_weight(shape=(input_size, output_size), initializer="random_normal", trainable=True)

	@tf.function
	def call(self, inputs_for_keys, inputs_for_values, inputs_for_queries):
		K = tf.tensordot(inputs_for_keys, self.K, 1)
		V = tf.tensordot(inputs_for_values, self.V, 1)
		Q = tf.tensordot(inputs_for_queries, self.Q, 1)

		K_T = tf.transpose(K, perm=[0,2,1])
		Q_times_K_T = tf.matmul(Q, K_T)
		scale = tf.math.sqrt(tf.cast(K.get_shape()[2], tf.float32))
		scaled_Q_K = tf.math.divide(Q_times_K_T, scale)
		result = tf.nn.softmax(scaled_Q_K)
		Z = tf.matmul(result, V)

		return Z

class Transformer_Block(tf.keras.layers.Layer):

	def __init__(self, emb_sz, is_decoder, multi_headed=False):

		super(Transformer_Block, self).__init__()

		self.ff_layer_1 = tf.keras.layers.Dense(emb_sz, activation='relu')
		self.ff_layer_2 = tf.keras.layers.Dense(emb_sz, activation=None)
		self.relu_layer = tf.keras.layers.Dense(emb_sz, activation='relu')
		self.self_atten = Atten_Head(emb_sz,emb_sz,use_mask=is_decoder) 
		self.is_decoder = is_decoder
		if self.is_decoder:
			self.self_context_atten = Atten_Head(emb_sz,emb_sz,use_mask=False)

		self.layer_norm = tf.keras.layers.LayerNormalization(axis=-1)

	@tf.function
	def call(self, inputs, context=None):
		# with av.trans_block(self.is_decoder):
		atten_out = self.self_atten(inputs,inputs,inputs)
		atten_out = tf.concat((atten_out, inputs), axis=1) #TODO change axis
		atten_normalized = self.layer_norm(atten_out)

		if self.is_decoder:
			assert context is not None, "Decoder blocks require context"
			context_atten_out = self.self_context_atten(context, context, atten_normalized)
			context_atten_out = tf.concat((context_atten_out, atten_normalized), axis=1) 
			atten_normalized = self.layer_norm(context_atten_out)

		ff_out = self.ff_layer_1(atten_normalized)
		ff_out = self.ff_layer_2(ff_out)
		ff_out = tf.concat((ff_out, atten_normalized), axis=1) 
		ff_norm = self.layer_norm(ff_out)
		ff_norm = self.relu_layer(ff_norm)
		
		return ff_norm
