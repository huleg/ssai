#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import matplotlib
matplotlib.use('Agg')
sys.path.append('scripts/build')
import matplotlib.pyplot as plt
from ssai import relax_precision, relax_recall
import cv2 as cv
import re
import glob
import numpy as np
import os
from os.path import basename
from os.path import exists
from multiprocessing import Queue, Process, Array

ch = 3
steps = 256
relax = 3
pad = 24
n_thread = 8

result_dir = 'results/Multi_Plain_Mnih_NN_S_ReLU_2015-02-06_12-20-13'
label_dir = 'data/mass_merged/test/map'
result_fns = glob.glob('%s/*.npy' % result_dir)
n_results = len(result_fns)

# all_positive = Array('d', n_results * ch * steps)
# all_prec_tp = Array('d', n_results * ch * steps)
# all_true = Array('d', n_results * ch * steps)
# all_recall_tp = Array('d', n_results * ch * steps)
all_positive = np.zeros((n_results, ch, steps), dtype=np.int64)
all_prec_tp = np.zeros((n_results, ch, steps), dtype=np.int64)
all_true = np.zeros((n_results, ch, steps), dtype=np.int64)
all_recall_tp = np.zeros((n_results, ch, steps), dtype=np.int64)


def makedirs(dname):
    if not exists(dname):
        os.makedirs(dname)


def get_pre_rec(positive, prec_tp, true, recall_tp, steps):
    pre_rec = []
    for t in range(steps):
        if positive[t] < prec_tp[t] or true[t] < recall_tp[t]:
            sys.exit('calculation is wrong')
        pre = float(prec_tp[t]) / \
            positive[t] if positive[t] > 0 else 0
        rec = float(recall_tp[t]) / true[t] if true[t] > 0 else 1
        pre_rec.append([pre, rec])
    pre_rec = np.asarray(pre_rec)
    breakeven_pt = np.abs(pre_rec[:, 0] - pre_rec[:, 1]).argmin()

    return pre_rec, breakeven_pt


def draw_pre_rec_curve(pre_rec, breakeven_pt):
    plt.clf()
    plt.plot(pre_rec[:, 0], pre_rec[:, 1])
    plt.plot(pre_rec[breakeven_pt, 0], pre_rec[breakeven_pt, 1],
             'x', label='breakeven: %f' % (pre_rec[breakeven_pt, 1]))
    plt.ylabel('recall')
    plt.xlabel('precision')
    plt.ylim([0.0, 1.1])
    plt.xlim([0.0, 1.1])
    plt.legend(loc='lower left')
    plt.grid(linestyle='--')


def worker_thread(result_fn_queue):
    while True:
        i, result_fn = result_fn_queue.get()
        if result_fn is None:
            break

        img_id = basename(result_fn).split('pred_')[-1].split('.tiff')[0]
        out_dir = '%s/evaluation/%s' % (result_dir, img_id)
        makedirs(out_dir)

        label = cv.imread('%s/%s.tif' %
                          (label_dir, img_id), cv.IMREAD_GRAYSCALE)
        pred = np.load(result_fn)
        label = label[pad:pad + pred.shape[0], pad:pad + pred.shape[1]]
        cv.imwrite('%s/label_%s.png' % (out_dir, img_id), label * 125)

        for c in range(ch):
            for t in range(1, steps):
                threshold = 1.0 / steps * t
                pred_vals = np.array(
                    pred[:, :, c] >= threshold, dtype=np.int32)
                label_vals = np.array(label == c, dtype=np.int32)

                all_positive[i, c, t] = np.sum(pred_vals)
                all_prec_tp[i, c, t] = relax_precision(
                    pred_vals, label_vals, relax)

                all_true[i, c, t] = np.sum(label_vals)
                all_recall_tp[i, c, t] = relax_recall(
                    pred_vals, label_vals, relax)

            pre_rec, breakeven_pt = get_pre_rec(
                all_positive[i, c], all_prec_tp[i, c],
                all_true[i, c], all_recall_tp[i, c], steps)

            draw_pre_rec_curve(pre_rec, breakeven_pt)
            plt.savefig('%s/pr_curve_%d.png' % (out_dir, c))
            np.save('%s/pre_rec_%d' % (out_dir, c), pre_rec)
            cv.imwrite('%s/pred_%d.png' % (out_dir, c), pred[:, :, c] * 255)

            print img_id, c, pre_rec[breakeven_pt]
    print 'thread finished'


if __name__ == '__main__':
    result_fn_queue = Queue()
    workers = [Process(target=worker_thread,
                       args=(result_fn_queue,)) for i in range(n_thread)]
    map(lambda w: w.start(), workers)
    [result_fn_queue.put((i, fn)) for i, fn in enumerate(result_fns)]
    [result_fn_queue.put((None, None)) for _ in range(n_thread)]
    map(lambda w: w.join(), workers)
    print 'all finished'

    all_positive = np.sum(all_positive, axis=0)
    all_prec_tp = np.sum(all_prec_tp, axis=0)
    all_true = np.sum(all_true, axis=0)
    all_recall_tp = np.sum(all_recall_tp, axis=0)
    for c in range(ch):
        print all_positive[c]
        print all_prec_tp[c]
        print all_true[c]
        print all_recall_tp[c]
        pre_rec, breakeven_pt = get_pre_rec(
            all_positive[c], all_prec_tp[c],
            all_true[c], all_recall_tp[c], steps)
        draw_pre_rec_curve(pre_rec, breakeven_pt)
        plt.savefig('%s/evaluation/pr_curve_%d.png' % (result_dir, c))
        np.save('%s/evaluation/pre_rec_%d' % (result_dir, c), pre_rec)

        print pre_rec[breakeven_pt]
