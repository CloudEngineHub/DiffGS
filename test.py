#!/usr/bin/env python3

import torch
import torch.utils.data 
from torch.nn import functional as F
import pytorch_lightning as pl
from pytorch_lightning.callbacks import ModelCheckpoint, Callback, LearningRateMonitor
from pytorch_lightning import loggers as pl_loggers

import os
import json, csv
import time
from tqdm.auto import tqdm
from einops import rearrange, reduce
import numpy as np
import trimesh
import warnings

from models import * 
from utils import evaluate, pointcloud
from diff_utils.helpers import * 

from utils.convert import convert

           
def test_generation():

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = CombinedModel.load_from_checkpoint(specs["modulation_ckpt_path"], specs=specs, strict=False) 
        ckpt = torch.load(specs["diffusion_ckpt_path"])
        new_state_dict = {}
        for k,v in ckpt['state_dict'].items():
            new_key = k.replace("diffusion_model.", "")
            new_state_dict[new_key] = v
        
        model.diffusion_model.load_state_dict(new_state_dict)
        model = model.cuda().eval()

    idx = 0
    for e in range(args.epoches):
        samples = model.diffusion_model.generate_unconditional(args.num_samples)
        plane_features = model.vae_model.decode(samples)
        for i in range(len(plane_features)):
            plane_feature = plane_features[i].unsqueeze(0)
            with torch.no_grad():
                print('create points fast')
                new_pc = pointcloud.create_pc_fast(model.gs_model, plane_feature, N=1024, max_batch=2**20, from_plane_features=True)
            new_pc_optimizer = pointcloud.pc_optimizer(model.gs_model, plane_feature.detach(), new_pc.clone().detach().cuda())            
            with torch.no_grad():
                new_pc = torch.cat([new_pc, new_pc_optimizer], dim=1)
                new_pc = new_pc.reshape(1, -1, 3).float()
                pred_color, pred_gs = model.gs_model.forward_with_plane_features(plane_feature, new_pc)
                gaussian = torch.zeros(new_pc.shape[1], 59).cpu()
                gaussian[:,:3] = new_pc[0]
                gaussian[:,3:51]
                gaussian[:,3:51] = pred_color[0]
                gaussian[:,51] = 2.9444
                gaussian[:,52:55] = 0.9 * torch.log(pred_gs[0,:,0:3])
                gaussian[:,55:59] = pred_gs[0,:,3:7]
                convert(gaussian.detach().cpu().numpy(), f"./generate/gaussian_{idx}.ply")
                idx = idx + 1

if __name__ == "__main__":

    import argparse

    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument(
        "--exp_dir", "-e", required=True,
        help="This directory should include experiment specifications in 'specs.json,' and logging will be done in this directory as well.",
    )

    arg_parser.add_argument("--num_samples", "-n", default=5, type=int, help='number of samples to generate and reconstruct')

    arg_parser.add_argument("--epoches", default=100, type=int, help='number of epoches to generate and reconstruct')

    arg_parser.add_argument("--filter", default=False, help='whether to filter when sampling conditionally')

    args = arg_parser.parse_args()
    specs = json.load(open(os.path.join(args.exp_dir, "specs.json")))
    print(specs["Description"])


    recon_dir = os.path.join(args.exp_dir, "recon")
    os.makedirs(recon_dir, exist_ok=True)
    

    if specs['training_task'] == 'combined':
        test_generation()
