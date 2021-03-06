import logging
import time
import os

import torch
import numpy as np
from tqdm import tqdm

from .multi_go_engine import MultiGoEngine
from .tester import Tester
from .multi_tester import MultiTester
from .teeny_go.teeny_go_network import TeenyGoNetwork

class Trainer(object):

    def __init__(self, network=None):

        # make sure network is inputed
        if network==None:
            raise ValueError("no network supplied")

        # initialize model
        self.network = network

        # initialize tester
        self.tester = Tester()

        # initlize multi tester
        self.multi_tester = MultiTester()

        # load game engine
        self.engine = MultiGoEngine()

        # initialize logger
        self.logger = logging.getLogger(name="Trainer")

        # save network attributes
        self.num_res = self.network.num_res_blocks
        self.num_channels = self.network.num_channels

        # set model name
        self.model_name = "Model-R{}-C{}".format(self.num_res, self.num_channels)

    # saves model to models file
    def save_model(self, version):
        path = "models/Model-R{}-C{}/".format(self.num_res, self.num_channels)
        filename = "Model-R{}-C{}-V{}.pt".format(self.num_res, self.num_channels, version)
        torch.save(self.network.state_dict(), path+filename)

    # loads model from models file
    def load_model(self, version):
        path = "models/Model-R{}-C{}/".format(self.num_res, self.num_channels)
        filename = "Model-R{}-C{}-V{}.pt".format(self.num_res, self.num_channels, version)
        self.network.load_state_dict(torch.load(path+filename))

    # saves data to data file
    def save_data(self, x, y, version):
        path = "data/Model-R{}-C{}/".format(self.num_res, self.num_channels)
        filenameX = "Model-R{}-C{}-V{}-DataX.pt".format(self.num_res, self.num_channels, version)
        filenameY = "Model-R{}-C{}-V{}-DataY.pt".format(self.num_res, self.num_channels, version)
        torch.save(x, path+filenameX)
        torch.save(y, path+filenameY)

    # loads data from data file
    def load_data(self, num_res, num_channel, version):
        path = "data/Model-R{}-C{}/".format(num_res, num_channel)
        filenameX = "Model-R{}-C{}-V{}-DataX.pt".format(num_res, num_channel, version)
        filenameY = "Model-R{}-C{}-V{}-DataY.pt".format(num_res, num_channel, version)
        x = torch.load(path+filenameX)
        y = torch.load(path+filenameY)

    # plays through n games, returns game data
    def play_through_games(self, num_games, is_cuda=False):

        # reset and clear engine
        self.engine.reset_games(num_games)

        if is_cuda:

            self.network.cuda()
            # main play loop
            while self.engine.is_playing_games():

                state_tensor = (torch.from_numpy(self.engine.get_active_game_states())).cuda().type(torch.cuda.FloatTensor)
                move_tensor = self.network.forward(state_tensor)
                torch.cuda.empty_cache()
                self.engine.take_game_step(move_tensor.cpu().detach().numpy())

        else:

            # main play loop
            while self.engine.is_playing_games():

                state_tensor = (torch.from_numpy(self.engine.get_active_game_states())).float()
                move_tensor = self.network.forward(state_tensor).detach().numpy()
                self.engine.take_game_step(move_tensor)

        # change game outcomes
        self.engine.finalize_game_data()

        # return game data tensors
        return self.engine.get_all_data()

    def train_self_play(self, num_games=100, iterations=1, skill_check=5, is_cuda=False):

        # assert inputs
        assert type(iterations)==int, "iterations must be an integer"
        assert type(num_games)==int, "number of games must be an integer"

        version = 1

        # loop through each iteration (index start at 1)
        for iter in range(1, iterations+1):

            print("Model-Trainer: Training Iteration {}".format(iter))
            print("Model-Trainer: Training Version {}".format(version))


            # play through games
            x, y = self.play_through_games(num_games=num_games, is_cuda=is_cuda)

            # convert to torch tensors
            x, y = (torch.from_numpy(x)), (torch.from_numpy(y))

            print(x.shape)


            ###############################################
            """
            if is_cuda:
                x = x.cuda().type(torch.cuda.FloatTensor)
                y = y.cuda().type(torch.cuda.FloatTensor)
            else:
                x = x.float()
                y = y.float()
            # train on new game data
            self.network.optimize(x, y, batch_size=2500, iterations=1, alpha=0.01)
            """
            ###############################################


            # save model
            self.save_model(version=version)

            # save game data
            self.save_data(x, y, version=version)

            # clear memory
            del(x)
            del(y)

            torch.cuda.empty_cache()

            if version >= 6:# == 0 and version >= 5:


                train_start = version-5

                train_end = version+1

                for i in range(10):
                    for file_num in tqdm(range(train_start, train_end)):
                        path = "data/Model-R{}-C{}/".format(self.num_res, self.num_channels)
                        filenameX = "Model-R{}-C{}-V{}-DataX.pt".format(self.num_res, self.num_channels, file_num)
                        filenameY = "Model-R{}-C{}-V{}-DataY.pt".format(self.num_res, self.num_channels, file_num)


                        x = torch.load(path+filenameX)
                        y = torch.load(path+filenameY)

                        x = x.cuda().type(torch.cuda.FloatTensor)
                        y = y.cuda().type(torch.cuda.FloatTensor)

                        self.network.optimize(x, y, batch_size=2500, iterations=1, alpha=0.01)

                        torch.cuda.empty_cache()

                        del(x)
                        del(y)

                        torch.cuda.empty_cache()



                if self.is_improved(version):
                    version += 1

                else:
                    version -= 1
                    self.load_model(version=version)
                    version += 1

            else:
                version += 1

            torch.cuda.empty_cache()

    def is_improved(self, version):

        # load models
        a1 = TeenyGoNetwork(num_channels=self.num_channels, num_res_blocks=self.num_res, is_cuda=True)
        a2 = TeenyGoNetwork(num_channels=self.num_channels, num_res_blocks=self.num_res, is_cuda=True)

        # load network parameters

        path = "models/Model-R{}-C{}/".format(self.num_res, self.num_channels)
        a1_filename = "Model-R{}-C{}-V{}.pt".format(self.num_res, self.num_channels, version)
        a2_filename = "Model-R{}-C{}-V{}.pt".format(self.num_res, self.num_channels, version-1)

        a1.load_state_dict(torch.load(path+a1_filename))
        a2.load_state_dict(torch.load(path+a2_filename))

        a1.cuda()
        a2.cuda()


        a1_wins_black, a2_wins_white, draws1 = self.multi_tester.play_through_games(a1, a2, num_games=250)
        a2_wins_black, a1_wins_white, draws2 = self.multi_tester.play_through_games(a2, a1, num_games=250)

        a1_wins = (a1_wins_black+a1_wins_white)/2
        a2_wins = (a2_wins_black+a2_wins_white)/2
        draws = (draws1 + draws2)/2

        print("Model-Tester: Model 1 : {} black wins, {} white wins, {} draws".format(a1_wins_black, a1_wins_white, draws))
        print("Model-Tester: Model 2 : {} black wins, {} white wins, {} draws".format(a2_wins_black, a2_wins_white, draws))

        if a1_wins+draws > 53: return True

        else: return False
