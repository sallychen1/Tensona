import tensorflow as tf
import numpy as np
from tensorflow.keras import Model
import os
import sys
from lstm_model import *
from encode import *
from preprocess import Data

class decode_model(lstm_model):
    def call(self, batched_source, batched_target, speaker_list, addressee_list, initial_state):
        """
        Runs the decoder model on one batch of source & target inputs

        :param batched_source: 2-D array of size (batch_size, sentence_max_length) that contains the batched, tokenized source scripts 
        :param batched_target: 2-D array of size (batch_size, sentence_max_length) that contains the batched, tokenized target scripts 
        :param speaker_list: 1-D array of size (batch_size) that contains speaker ids
        :param addressee_list: 1-D array of size (batch_size) that contains addressee ids

        :return loss: a tensor that contains the loss of this batch
        :       probs_list: a 2-D tensor that contains probabilities calculated for each column of 
                            words in target, shape = (sentence_max_length-1, batch_size, num_vocab)

        """
     
        source_ebd = tf.nn.embedding_lookup(self.source_embedding, batched_source)
        encoded_outputs, initial_state = self.encoder(source_ebd, initial_state=initial_state)
        losses = []
        probs_list = []
        
        for i in range(tf.shape(batched_target)[1]-1):
            target_ebd = tf.nn.embedding_lookup(self.target_embedding, batched_target[:, i]) # shape = (batch_size, 1, embed_size)
            probs, initial_state = self.decoder(encoded_outputs, initial_state, target_ebd, speaker_list, addressee_list)
            labels = tf.squeeze(batched_target[:, i+1]) 
            l = self.loss_func(probs, labels)
            losses.append(l)
            probs_list.append(probs)
        losses = tf.convert_to_tensor(losses) 
        loss = tf.reduce_sum(losses)
        probs_list = tf.convert_to_tensor(probs_list)

        # # Get the start point of beam search
        # start=tf.nn.embedding_lookup(self.target_embedding, batched_target[:,0])
        # init_probs,init_state= self.decoder(encoded_outputs, initial_state, start, speaker_list, addressee_list)

        # # Perform beam search
        # probs_list = self.beam_search(init_probs, init_state, encoded_outputs,speaker_list, addressee_list)
        return losses, probs_list

    def beam_search(self,init_probs, init_state, encoded_outputs, speaker_list, addressee_list):
        """
        Performs beam search to produce the top N candidates

        :param init_probs: word prediction probabilities, 2D tensor (batch_size, num_vocab)
        :param init_state: hidden state from previous iterations, tuple of (batch_size x hidden state)

        :return best_cand: best N candidates represented as probabilities
        """

        # Initialize first round of beam search
        init_probs = tf.nn.log_softmax(init_probs) #log_probs in the scoring function
        all_probs, all_candidates = tf.nn.top_k(init_probs, k = self.beam_size,sorted = False) #shape = (batch_size, beam_size)
        all_candidates = tf.expand_dims(all_candidates,axis = 2) # shape = (batch_size, beam_size, 1) so it can be passed into decoder

        # Stores each candidate & its score
        final_cand = [[list(), 0.0]]
        
        step = 0
        # At each time step, examine all B × B possible next-word candidates
        while  step <= self.sentence_max_length:
            # cur_cand = [[list(), 0.0]]
            for b in range (self.beam_size):
                # Run decoder at the b-th column to get new info 
                probs,states = self.decoder(encoded_outputs,init_state,
                                tf.nn.embedding_lookup(self.target_embedding,all_candidates[:,b,-1]),
                                speaker_list,addressee_list)
                probs = tf.nn.log_softmax(probs)

                topb_probs,topb_cand = tf.nn.top_k(probs,k = self.beam_size, sorted = False)
                
                # TODO: Convert this into tf & simplify
                topb_probs *= tf.expand_dims((all_candidates[:,b]!=1).numpy().all(axis=1), axis = 1)
                topb_probs += tf.expand_dims(all_probs[:,b], axis = 1)
                topb_cand = tf.concat((all_candidates[:,b].unsqueeze(1).expand(all_candidates.size()),topb_cand.unsqueeze(2)),2)

                # TODO: Alt approach - Add all hypothesis ending with an EOS token to the N-best list, Preserve the top-B unfinished hypotheses
                # for row in range(len(all_candidates[:,b])):
                #     # Add all hypothesis ending with an EOS token to the N-best list
                #     if all_candidates[:,b][row] == 1: 
                #         c = all_candidates[row]
                #         final_cand.append([c,probs[:,b][row]])
                #     else:
                #         # Preserve the top-B unfinished hypotheses
                #         topb_prob,topb_cand = tf.nn.top_k(probs,k = self.beam_size, sorted = False)
                #         cur_cand.append([topb_cand[:,b],topb_prob[:,b]])

                if b==0:
                    cur_probs = topb_probs
                    cur_candidates = topb_cand
                    hs = tf.expand_dims(states[0],axis = 2)
                    cs = tf.expand_dims(states[1],axis = 2)

                else:
                    cur_probs = tf.concat((cur_probs,topb_probs),1)
                    cur_cand = tf.concat((cur_cand,topb_cand),1)
                    hs = tf.concat((hs,tf.expand_dims(states[0],axis = 2)),2)
                    cs = tf.concat((cs,tf.expand_dims(states[1],axis = 2)),2)

                # Move to the next word position.
                step += 1
                if step == self.sentence_max_length:
                    break
    
        # Rank the candidates then return the top k candidates
        best_cand = sorted(final_cand, key=lambda tup:tup[1])[:self.beam_size]
        # TODO: reshape to (sentence_max_length-1, batch_size, num_vocab)
        # return best_cand
        pass
    
    def get_score(self, candidate):
        """
        Helper function to get the score of a specific candidate. 
        Linearly combines a length penalty and the log likelihood of the source given the target

        :param candidate
        :return score

        """   
        # 1. log of: prob of the generated response given the message and the respondent’s speaker ID.    
        # 2. lamda * log of: prob of message given the generated response
        # 3. penalty weight * length of target     
        # score = 1 + 2 + 3
        pass

    def tf_beam_search(self, initial_state, beam_width):
        # TODO: figure out correct input 
        top_candidates, logProb =  tf.nn.ctc_beam_search_decoder(inputs = initial_state, 
                sequence_length = ([self.sentence_max_length]*self.batch_size), beam_width=self.beam_size, 
                top_paths=self.beam_size)

        print("\nTOP CANDIDATES = ",top_candidates)
        print("\nTOP CANDIDATES SHAPE = ",tf.shape(top_candidates))

        # TODO: figure out correct dimensions 
        top_candidates = tf.transpose(top_candidates, perm=[0, 2, 1])
        # return top_candidates 
        pass
    
class decode_params():
	def __init__(self):
		self.data_folder_path = '../data'
		self.friends_output_file_name = 'output.csv'

		self.lr_rate = 0.0005
		self.embed_size = 256
		self.batch_size = 128
		self.hidden_sz = 512
		self.start_halve = 5
		self.dropout = 0.1

		self.speaker_mode = True
		self.addressee_mode = True
		
		self.sentence_max_length = 20
		self.max_epochs = 1

class decode_model(tf.keras.Model):
    def __init__(self, params, data, is_speaker, is_friends):
        # self.model = beam_decoder(self.params, self.num_vocab, self.num_characters, is_speaker)
        self.is_speaker = is_speaker
        self.is_friends = is_friends
        if is_friends==True:
            friends_data_dict = self.data.friends_tsv(num_seasons=10)
            self.data_dict = self.data.cleanup_and_build_dict(friends_data_dict)
            self.num_characters = self.data.num_characters
        else:
            dialogue_data_dict = self.data.dialogue_tsv()
            self.data_dict = self.data.build_dialogue_dict(dialogue_data_dict)
            self.num_characters = self.data.num_characters
        self.params = params
        self.model = decode_model(params, num_vocab, num_characters, self.is_speaker)

	# def read_encoder(self):
	# 	self.voc_decode = dict()
	# 	with open(path.join(self.params.data_folder,self.params.dictPath),'r') as doc:
	# 		for line in doc:
	# 			self.voc_decode[len(self.voc_decode)] = line.strip()

	# def id2word(self, ids):
	# 	### For raw-word data:
	# 	# self.voc_decode[len(self.voc_decode)] = '[unknown]'
	# 	tokens = []
	# 	for i in ids:
	# 		try:
	# 			word = self.voc_decode[int(i)-self.params.special_word]
	# 			tokens.append(word)
	# 		except KeyError:
	# 			break
	# 	return " ".join(tokens)
    

    def decode(self):
		num_epochs = 0
		while num_epochs < self.params.max_epochs:
			start_index = 0
			while (start_index + self.params.batch_size) < len(self.test_data[0]):
				# Read in batched test_data
				sources, targets, speakers, addressees = self.data.read_batch(self.test_data, start_index, mode='test')

if __name__ == '__main__':

    params = decode_params()
    data = Data(params)
    print('decoder.py: created params and data')

    friends_data = data.friends_tsv(num_seasons=10)
    data_dict = data.cleanup_and_build_dict(friends_data)
    num_characters = data.num_characters
    num_vocab = len(list(data.vocab_dict.keys()))

    if len(sys.argv) != 3 or sys.argv[1] not in {"SPEAKER", "SPEAKER_ADDRESSEE"} or sys.argv[2] not in {"FRIENDS", "DIALOGUE"}:
		print("USAGE: python decode.py <Model Type> <Dataset>")
		print("<Model Type>: [SPEAKER / SPEAKER_ADDRESSEE]")
		print("<Model Type>: [FRIENDS / DIALOGUE]")
		exit()

    if sys.argv[1] == "SPEAKER":
		is_speaker = True
    elif sys.argv[1] == "SPEAKER_ADDRESSEE":
		is_speaker = False

    self.model = decode_model(params, data, is_speaker)

    # self.ReadDict()
    # self.Data=data(self.params,self.voc)
    # self.Model = lstm_decoder(self.params,len(self.voc),self.Data.EOT)
    # print('decode.py: created decoder')
    # self.readModel(self.params.model_folder,self.params.model_name)
    # self.Model.to(self.device)
    # self.ReadDictDecode()

    # self.output=path.join(self.params.output_folder,self.params.log_file)
    # if self.output!="":
    #     with open(self.output,"w") as selfoutput:
    #         selfoutput.write("")