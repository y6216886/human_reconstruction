# Copyright (c) Facebook, Inc. and its affiliates. All rights reserved.

import torch
import torch.nn as nn
import pytorch_lightning as pl
from termcolor import colored
import torch.nn.functional as F

# class MLP(pl.LightningModule): ##1413
#     def __init__(self, filter_channels, name=None, res_layers=[], norm='group', last_op=None, args=None):

#         super(MLP, self).__init__()
#         self.args=args
#         if self.args.mlp_first_dim!=0:
#             filter_channels[0]=self.args.mlp_first_dim
#             print(colored("I have modified mlp filter channles{}".format(filter_channels),"red"))
#         self.filters = nn.ModuleList()
#         self.norms = nn.ModuleList()
#         self.res_layers = res_layers
#         self.norm = norm
#         self.last_op = last_op
#         self.name = name
#         self.activate = nn.LeakyReLU(inplace=True)
#         if self.args.mlpSe:
#             self.se_conv = nn.ModuleList()
#             for filters_nums_ in filter_channels[1:-1]:
#                 self.se_conv.append(SpatialSELayer(filters_nums_))  #1449 gpu memory for bs 2
#                 # self.se_conv.append(ChannelSELayer(filters_nums_))  #1457 gpu memory for bs 2
#         elif self.args.mlpSev1:
#             self.se_conv = nn.ModuleList()
#             for filters_nums_ in filter_channels[1:-1]:
#                 # self.se_conv.append(SpatialSELayer(filters_nums_))  #1449 gpu memory for bs 2
#                 self.se_conv.append(ChannelSELayer(filters_nums_))  #1457 gpu memory for bs 2
#         # elif self.args.mlpSemax:
#         #     self.se_conv = nn.ModuleList()
#         #     for filters_nums_ in filter_channels[1:-1]:
#         #         # self.se_conv.append(SpatialSELayer(filters_nums_))  #1449 gpu memory for bs 2
#         #         self.se_conv.append(ChannelSELayer(filters_nums_)) 

#         for l in range(0, len(filter_channels) - 1):
#             if l in self.res_layers:
#                 self.filters.append(
#                     nn.Conv1d(filter_channels[l] + filter_channels[0], filter_channels[l + 1], 1)
#                 )
#             else:
#                 self.filters.append(nn.Conv1d(filter_channels[l], filter_channels[l + 1], 1))

#             if l != len(filter_channels) - 2:
#                 if norm == 'group':
#                     self.norms.append(nn.GroupNorm(32, filter_channels[l + 1]))
#                 elif norm == 'batch':
#                     self.norms.append(nn.BatchNorm1d(filter_channels[l + 1]))
#                 elif norm == 'instance':
#                     self.norms.append(nn.InstanceNorm1d(filter_channels[l + 1]))
#                 elif norm == 'weight':
#                     self.filters[l] = nn.utils.weight_norm(self.filters[l], name='weight')
#                     # print(self.filters[l].weight_g.size(),
#                     #       self.filters[l].weight_v.size())
#         self.len_filter=len(self.filters)

#     def forward(self, feature):
#         '''
#         feature may include multiple view inputs
#         args:
#             feature: [B, C_in, N]
#         return:
#             [B, C_out, N] prediction
#         '''
#         y = feature
#         tmpy = feature

#         for i, f in enumerate(self.filters):

#             y = f(y if i not in self.res_layers else torch.cat([y, tmpy], 1))
#             if i != len(self.filters) - 1:
#                 if self.norm not in ['batch', 'group', 'instance']:
#                     y = self.activate(y)
#                 else:
#                     y = self.activate(self.norms[i](y))
#             if self.args.mlpSe or self.args.mlpSev1:
#                 if i!=self.len_filter-1:
#                     y=self.se_conv[i](y)
#         if self.last_op is not None:
#             y = self.last_op(y)

#         return y

class MLP_uncertainty(pl.LightningModule):
    def __init__(self):

        super(MLP_uncertainty, self).__init__()
        self.net=nn.Sequential(nn.Conv1d(1, 4, 1),
                                            nn.ELU(inplace=True),
                                            nn.Dropout(p=0.2),
                                            nn.Conv1d(4, 8, 1),
                                            nn.ELU(inplace=True),
                                            nn.Dropout(p=0.2),
                                            nn.Conv1d(8, 1, 1),
                )
        for m in self.modules():
            if isinstance(m, nn.Conv1d):
                m.bias.data.zero_()
    def forward(self,x):
        return self.net(x)
        
class MLP(pl.LightningModule):
    def __init__(self, filter_channels, name=None, res_layers=[], norm='group', last_op=None, args=None):

        super(MLP, self).__init__()
        self.args=args
        self.len_channels=len(filter_channels)
        if args.mlp_first_dim!=0:
            filter_channels[0]=args.mlp_first_dim
        print(colored("I have modified mlp filter channles{}".format(filter_channels),"red"))
        # if args.uncertainty:
        #     print("uncertainty")
        #     filter_channels[-1]+=1  #We follow the authors’ suggestion and train the network to predict the log of the observation noise scalar, s, for numerical stability.
        self.filters = nn.ModuleList()
        self.norms = nn.ModuleList()
        self.res_layers = res_layers
        self.norm = norm
        self.last_op = last_op
        self.name = name
        if self.args.use_clip:
            self.clip_feature=768
            self.clip_fuse_layer=[int(i) for i in self.args.clip_fuse_layer] #[1,2,3]
            print("clip_fuse_layer", self.clip_fuse_layer)

        self.activate = nn.LeakyReLU(inplace=True)
        assert [self.args.mlpSe, self.args.mlpSev1, self.args.mlpSemax].count(True) in [0,1], "mlp se strategy cannot be embodied simultaneously"
        self.se_start_channel=self.args.se_start_channel
        self.se_end_channel=self.args.se_end_channel
        assert self.se_end_channel <self.len_channels
        assert self.se_start_channel >=0
        if self.args.mlpSe: ##this strategy yields best results, while not surpasses baseline yet. 
            self.se_conv = nn.ModuleList()
            for filters_nums_ in filter_channels[self.se_start_channel:self.se_end_channel]:
                # self.se_conv.append(SpatialSELayer(filters_nums_))  #1449 gpu memory for bs 2
                # self.se_conv.append(ChannelSELayer(filters_nums_))  #1457 gpu memory for bs 2
                self.se_conv.append(SCSEModule(filters_nums_, self.args.se_reduction, self.args))
        elif self.args.mlpSev1:
            self.se_conv = nn.ModuleList()
            for filters_nums_ in filter_channels[self.se_start_channel:self.se_end_channel]:
                # self.se_conv.append(SpatialSELayer(filters_nums_))  #1449 gpu memory for bs 2
                self.se_conv.append(ChannelSELayer(filters_nums_, self.args.se_reduction))  #1457 gpu memory for bs 2
        elif self.args.mlpSemax:
            self.se_conv_spatial = nn.ModuleList()
            self.se_conv_channel = nn.ModuleList()
            for filters_nums_ in filter_channels[self.se_start_channel:self.se_end_channel]:
                self.se_conv_spatial.append(SpatialSELayer(filters_nums_))  #1449 gpu memory for bs 2
                self.se_conv_channel.append(ChannelSELayer(filters_nums_)) 
        if self.args.use_clip:
            for l in range(0, len(filter_channels) - 1):
                if l in self.res_layers and l not in self.clip_fuse_layer:
                    self.filters.append(
                        nn.Conv1d(filter_channels[l] + filter_channels[0], filter_channels[l + 1], 1)
                    )
                elif l in self.res_layers and l in self.clip_fuse_layer:
                    self.filters.append(nn.Conv1d(filter_channels[l]+ filter_channels[0] + self.clip_feature, filter_channels[l + 1], 1))
                elif l not in self.res_layers and l in self.clip_fuse_layer:
                    self.filters.append(nn.Conv1d(filter_channels[l] + self.clip_feature, filter_channels[l + 1], 1))
                elif l not in self.res_layers and l not in self.clip_fuse_layer:
                    self.filters.append(nn.Conv1d(filter_channels[l], filter_channels[l + 1], 1))

                if l != len(filter_channels) - 2:
                    if norm == 'group':
                        self.norms.append(nn.GroupNorm(32, filter_channels[l + 1]))
                    elif norm == 'batch':
                        self.norms.append(nn.BatchNorm1d(filter_channels[l + 1]))
                    elif norm == 'instance':
                        self.norms.append(nn.InstanceNorm1d(filter_channels[l + 1]))
                    elif norm == 'weight':
                        self.filters[l] = nn.utils.weight_norm(self.filters[l], name='weight')
                        # print(self.filters[l].weight_g.size(),
                        #       self.filters[l].weight_v.size())
        else:
            for l in range(0, len(filter_channels) - 1):
                if l in self.res_layers:
                    self.filters.append(
                        nn.Conv1d(filter_channels[l] + filter_channels[0], filter_channels[l + 1], 1)
                    )
                else:
                    self.filters.append(nn.Conv1d(filter_channels[l], filter_channels[l + 1], 1))

                if l != len(filter_channels) - 2:
                    if norm == 'group':
                        self.norms.append(nn.GroupNorm(32, filter_channels[l + 1]))
                    elif norm == 'batch':
                        self.norms.append(nn.BatchNorm1d(filter_channels[l + 1]))
                    elif norm == 'instance':
                        self.norms.append(nn.InstanceNorm1d(filter_channels[l + 1]))
                    elif norm == 'weight':
                        self.filters[l] = nn.utils.weight_norm(self.filters[l], name='weight')
                        # print(self.filters[l].weight_g.size(),
                        #       self.filters[l].weight_v.size())
        self.len_filter=len(self.filters)
        if self.args.dropout!=0: self.dropout=nn.Dropout(self.args.dropout)
        if self.args.uncertainty:
            self.mlp_uncertainty=MLP_uncertainty()

    def forward(self, feature, clip_feature=None): ##todo fuse clip feature into
        '''
        feature may include multiple view inputs
        args:
            feature: [B, C_in, N]
        return:
            [B, C_out, N] prediction
        '''
        y = feature
        if self.args.use_clip: clip_feature=clip_feature.unsqueeze(-1).repeat(1,1,8000)
        tmpy = feature
        # len_=len(self.filters)
        j=0
        for i, f in enumerate(self.filters):
            ####se net
            if self.args.mlpSe or self.args.mlpSev1:
                if i in range(self.se_start_channel,self.se_end_channel):
                    y=self.se_conv[j](y) 
                    j+=1
            elif self.args.mlpSemax:
                if i in range(self.se_start_channel,self.se_end_channel):
                    y_spa=self.se_conv_spatial[j](y) ##
                    y_cha=self.se_conv_channel[j](y) ##
                    y=torch.max(y_spa, y_cha)
                    j+=1
            #####
            if self.args.use_clip and i in self.clip_fuse_layer:
                input=torch.cat([y, clip_feature], 1) if i not in self.res_layers else torch.cat([y, tmpy, clip_feature], 1)
                if self.args.dropout!=0 and self.training and i>0: y= self.dropout(y)
                y = f(input)
            else: 
                input=y if i not in self.res_layers else torch.cat([y, tmpy], 1)
                if self.args.dropout!=0 and self.training and i>0: 
                    y= self.dropout(y)
                y = f(input)

            ###activation
            if i != len(self.filters) - 1:
                if self.norm not in ['batch', 'group', 'instance']:
                    y = self.activate(y)
                else:
                    y = self.activate(self.norms[i](y))
            ###
##bug do not activate the last channel

        if self.last_op is not None:
            y = self.last_op(y)
        if self.args.uncertainty:
            y_uncertainty=self.mlp_uncertainty(y)
            return torch.cat([y,y_uncertainty],dim=1)
        return y
    


# class MLP_v1(pl.LightningModule):
#     def __init__(self, filter_channels, name=None, res_layers=[], norm='group', last_op=None, args=None):

#         super(MLP, self).__init__()
#         self.args=args
#         if args.mlp_first_dim!=0:
#             filter_channels[0]=args.mlp_first_dim
#             print(colored("I have modified mlp filter channles{}".format(filter_channels),"red"))
#         self.filters = nn.ModuleList()
#         self.norms = nn.ModuleList()
#         self.res_layers = res_layers
#         self.norm = norm
#         self.last_op = last_op
#         self.name = name
#         self.activate = nn.LeakyReLU(inplace=True)
#         assert [self.args.mlpSe, self.args.mlpSev1, self.args.mlpSemax].count(True) in [0,1], "mlp se strategy cannot be embodied simultaneously"
#         if self.args.mlpSe:
#             self.se_conv = nn.ModuleList()
#             for filters_nums_ in filter_channels[1:-1]:
#                 self.se_conv.append(SpatialSELayer(filters_nums_))  #1449 gpu memory for bs 2
#                 # self.se_conv.append(ChannelSELayer(filters_nums_))  #1457 gpu memory for bs 2
#         elif self.args.mlpSev1:
#             self.se_conv = nn.ModuleList()
#             for filters_nums_ in filter_channels[1:-1]:
#                 # self.se_conv.append(SpatialSELayer(filters_nums_))  #1449 gpu memory for bs 2
#                 self.se_conv.append(ChannelSELayer(filters_nums_))  #1457 gpu memory for bs 2
#         elif self.args.mlpSemax:
#             self.se_conv_spatial = nn.ModuleList()
#             self.se_conv_channel = nn.ModuleList()
#             for filters_nums_ in filter_channels[1:-1]:
#                 self.se_conv_spatial.append(SpatialSELayer(filters_nums_))  #1449 gpu memory for bs 2
#                 self.se_conv_channel.append(ChannelSELayer(filters_nums_)) 

#         for l in range(0, len(filter_channels) - 1):
#             if l in self.res_layers:
#                 self.filters.append(
#                     nn.Conv1d(filter_channels[l] + filter_channels[0], filter_channels[l + 1], 1)
#                 )
#             else:
#                 self.filters.append(nn.Conv1d(filter_channels[l], filter_channels[l + 1], 1))

#             if l != len(filter_channels) - 2:
#                 if norm == 'group':
#                     self.norms.append(nn.GroupNorm(32, filter_channels[l + 1]))
#                 elif norm == 'batch':
#                     self.norms.append(nn.BatchNorm1d(filter_channels[l + 1]))
#                 elif norm == 'instance':
#                     self.norms.append(nn.InstanceNorm1d(filter_channels[l + 1]))
#                 elif norm == 'weight':
#                     self.filters[l] = nn.utils.weight_norm(self.filters[l], name='weight')
#                     # print(self.filters[l].weight_g.size(),
#                     #       self.filters[l].weight_v.size())
#         self.len_filter=len(self.filters)

#     def forward(self, feature):
#         '''
#         feature may include multiple view inputs
#         args:
#             feature: [B, C_in, N]
#         return:
#             [B, C_out, N] prediction
#         '''
#         y = feature
#         tmpy = feature
#         len_=len(self.filters)
#         for i, f in enumerate(self.filters):

#             y = f(y if i not in self.res_layers else torch.cat([y, tmpy], 1))
#             if i != len(self.filters) - 1:
#                 if self.norm not in ['batch', 'group', 'instance']:
#                     y = self.activate(y)
#                 else:
#                     y = self.activate(self.norms[i](y))
#             if self.args.mlpSe or self.args.mlpSev1:
#                 if i!=self.len_filter-1:
#                     y=self.se_conv[i](y) ##bug do not activate the last channel
#             elif self.args.mlpSemax:
#                 if i!=self.len_filter-1:
#                     y_spa=self.se_conv_spatial[i](y) ##
#                     y_cha=self.se_conv_channel[i](y) ##
#                     y=torch.max(y_spa, y_cha)



#         if self.last_op is not None:
#             y = self.last_op(y)

#         return y
    

class SpatialSELayer(nn.Module):
    """
    Re-implementation of SE block -- squeezing spatially and exciting channel-wise described in:
        *Roy et al., Concurrent Spatial and Channel Squeeze & Excitation in Fully Convolutional Networks, MICCAI 2018*
    """

    def __init__(self, num_channels):
        """
        :param num_channels: No of input channels
        """
        super(SpatialSELayer, self).__init__()
        self.conv = nn.Conv1d(num_channels, 1, 1)
        self.sigmoid = nn.Sigmoid()

    def forward(self, input_tensor, weights=None):
        """
        :param weights: weights for few shot learning
        :param input_tensor: X, shape = (batch_size, num_channels, H)
        :return: output_tensor
        """
        # spatial squeeze
        batch_size, channel, a= input_tensor.size()


 
        out = self.conv(input_tensor)
        squeeze_tensor = self.sigmoid(out)

        # spatial excitation
        squeeze_tensor = squeeze_tensor.view(batch_size, 1, a)
        output_tensor = torch.mul(input_tensor, squeeze_tensor)
        return output_tensor



class ChannelSELayer(nn.Module):
    """
    Re-implementation of Squeeze-and-Excitation (SE) block described in:
        *Hu et al., Squeeze-and-Excitation Networks, arXiv:1709.01507*
    """

    def __init__(self, num_channels, reduction_ratio=2):
        """
        :param num_channels: No of input channels
        :param reduction_ratio: By how much should the num_channels should be reduced
        """
        super(ChannelSELayer, self).__init__()
        num_channels_reduced = num_channels // reduction_ratio
        self.reduction_ratio = reduction_ratio
        self.fc1 = nn.Linear(num_channels, num_channels_reduced, bias=True)
        self.fc2 = nn.Linear(num_channels_reduced, num_channels, bias=True)
        # self.relu = nn.ReLU()
        self.sigmoid = nn.Sigmoid()

    def forward(self, input_tensor):
        """
        :param input_tensor: X, shape = (batch_size, num_channels, H, W)
        :return: output tensor
        """
        batch_size, num_channels, H = input_tensor.size()
        # Average along each channel
        squeeze_tensor = input_tensor.view(batch_size, num_channels, -1).mean(dim=2) ###cannot mix features of different points toghther

        # channel excitation
        # fc_out_1 = self.relu(self.fc1(squeeze_tensor))
        fc_out_1 = self.fc1(squeeze_tensor)
        fc_out_2 = self.sigmoid(self.fc2(fc_out_1))

        a, b = squeeze_tensor.size()
        output_tensor = torch.mul(input_tensor, fc_out_2.view(a, b, 1))
        return output_tensor

class SCSEModule(nn.Module):
    def __init__(self, in_channels, reduction=16, args=None):
        super().__init__()

        self.args=args
        if self.args.cse:
                self.cSE = nn.Sequential(
            nn.AdaptiveAvgPool1d(1),
            nn.Conv1d(in_channels, in_channels // reduction, 1),
            nn.ReLU(inplace=True),
            nn.Conv1d(in_channels // reduction, in_channels, 1),
            nn.Sigmoid(),
        )
        if self.args.sse:
            self.sSE = nn.Sequential(nn.Conv1d(in_channels, 1, 1), nn.Sigmoid())
    def forward(self, x):
        y=0
        if self.args.cse:
            cse=self.cSE(x)
            y+=x * cse
        if self.args.sse:
            sse=self.sSE(x)
            y+= x * sse
        return y


if __name__=="__main__":
    import os
    os.environ["CUDA_VISIBLE_DEVICES"]="2"
    class args_():
        def __init__(self) -> None:
            self.test_code=True
            self.mlp_first_dim=12
            self.mlpSev1=False
            self.mlpSe=True
            self.mlpSemax=False
            self.uncertainty=False
            self.use_clip=False
            self.dropout=0.2
            self.se_start_channel=1
            self.se_end_channel=4
            self.se_reduction=16
    args_=args_()
    net=MLP(filter_channels=[12,128,256,128,1], res_layers=[2,4] ,args=args_).cuda()
    # net=MLP(filter_channels=[12,128,256,128,1], args=args_).cuda()
    input=torch.randn(2,12,8000).cuda()
    input_clip=torch.randn(2,768).cuda()
    print(net(input, input_clip).size())
    print(1)