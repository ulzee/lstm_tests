
DATA_DIR = "/beegfs/ua349/lstm/Penn_Action"

frames_dir = DATA_DIR + '/frames'
labels_dir = DATA_DIR + '/labels'

import os, sys
from scipy.io import loadmat
from random import shuffle

def gather_videos(SEQ_LEN = 4, still=False):
	refs = []


	# [nose, neck, Rsho, Relb, Rwri, Lsho, Lelb, Lwri, Rhip, Rkne, Rank, Lhip, Lkne, Lank, Leye, Reye, Lear, Rear, pt19]
	# coco_incl = [0, None, 1, 3, 5, 2, 4, 6, 7, 9, 11, 8, 10, 12, None, None, None, None, None]
	coco_incl = [0, None, 1, 3, 5, 2, 4, 6, 7, 9, 11, 8, 10, 12, None, None, None, None]
	# TODO: 19th entry should be a maskish thing...?

	frame_folders = os.listdir(frames_dir)
	for __fii, fldr in enumerate(sorted(frame_folders, key=lambda val: int(val))):

		sys.stdout.write('%d/%d ~ %d\r' % (__fii, len(frame_folders), len(refs)))
		sys.stdout.flush()

		flpath = '%s/%s' % (frames_dir, fldr)
		imgs = [fl for fl in os.listdir(flpath)]
		imgs = sorted(imgs, key=lambda val: int(val.split('.')[0]))

		lblpath = '%s/%s' % (labels_dir, fldr)
		mat = loadmat(lblpath)
		xs, ys, bbox = mat['x'], mat['y'], mat['bbox']
		vis, dim = mat['visibility'], mat['dimensions']

		# for bii in range(0, len(imgs), SEQ_LEN):
		for bii in range(0, len(imgs), SEQ_LEN):
			ref = {
				'frames': [],
	#             'labels': [],
				'boxes': [],
	#             'local_coords': [],
				'coords': [],
				'coco_coords': [],
				'visibility': [],
			}


			if bii + SEQ_LEN >= len(imgs):
				rng = range(len(imgs) - SEQ_LEN, len(imgs))
			else:
				rng = range(bii, bii+SEQ_LEN)
			assert rng is not None

			if still:
				rng = [bii] * SEQ_LEN # all the same ind
			for ii in rng:

				assert ii < len(xs)
				ref['frames'].append('%s/%s' % (flpath, imgs[ii]))

				try:
					# case where last bbox can be missing sometimes
					assert ii < len(bbox)
					box = bbox[ii]
				except:
					print('WARN: Missing bbox %s' % lblpath)
					print()
					box = bbox[ii-1] # just sub in last frame

				ref['boxes'].append(box)
				coords = []
				for (xx, yy) in zip(xs[ii], ys[ii]):
					xx = max(0, xx-1)
					yy = max(0, yy-1)

					if xx == 0 or yy == 0:
						# invalid coord
						coords.append((-1, -1))
					else:
						coords.append((xx, yy))

				ref['coords'].append(coords)
				coco_coords = [None if ind is None else coords[ind] for ind in coco_incl]
				ref['coco_coords'].append(coco_coords)
				ref['visibility'].append(vis[ii])
			assert len(ref['frames']) == SEQ_LEN
			assert len(ref['coords']) == SEQ_LEN
			assert len(ref['coco_coords']) == SEQ_LEN

			refs.append(ref)
	shuffed = refs
	shuffle(shuffed)
	return [shuffed, refs]

import cv2
from cv2 import imread
import numpy as np
import random
def size_image(img, bbox, size=368):
	img = img.astype(np.float32)

	# zoom = 1 / random.uniform(1.25, 1.75) # x1.5 ~ x2.0
	zoom = 1 / random.uniform(1.0, 1.25) # x1.5 ~ x2.0
	targ = size * zoom
	half = targ / 2

	cx, cy = (bbox[2] + bbox[0]) / 2, (bbox[3] + bbox[1]) / 2

	x0, y0 = max(0, cx - half), max(0, cy - half)
	region = img[int(y0):int(y0+targ), int(x0):int(x0+targ)]
	maxlen = max(region.shape[0], region.shape[1])

	region = cv2.resize(region, (0,0), fx=368 / maxlen, fy=368 / maxlen)
	assert region.shape[0] == size or region.shape[1] == size

	canvas = np.zeros((size, size, 3))

	# center image again b/c region is not always a square
	dx, dy = 0, 0
	if region.shape[0] > region.shape[1]:
		dx = int((size - region.shape[1]) / 2)
	else:
		dy = int((size - region.shape[0]) / 2)

	canvas[dy:dy+region.shape[0], dx:dx+region.shape[1]] = region

	return canvas, (zoom, targ, (x0, y0), (dx, dy))

	# for frame in range()

from scipy.ndimage import gaussian_filter as blur

def create_heatmaps(coords, spec, size=46,dims=19):
	(zoom, targ, (x0, y0), (dx, dy)) = spec
	canvas = np.zeros((size, size, dims))

	for ii, coord in enumerate(coords):
		if coord is None:
			continue

		(xx, yy) = coord
		if xx == -1 or yy == -1:
			# invalid coord - DNE in image
			continue

		shrink = size / 368
		rx = int((dx + (xx - x0) / zoom) * shrink)
		ry = int((dy + (yy - y0) / zoom) * shrink)

		if rx >= size or ry >= size:
			continue
		if rx < 0 or ry < 0:
			continue

		canvas[ry, rx, ii] = 1
		img = blur(canvas[:, :, ii], sigma=1)
		canvas[:, :, ii] = img / np.max(img)

		canvas[ry, rx, -1] = 1 # sum mask

	assert np.max(canvas[:, :, -1]) <= 1.0
	img = blur(canvas[:, :, -1], sigma=1)
	img /= np.max(img)
	inv = 1 - img
	canvas[:, :, -1] = inv

	return canvas

def create_mask(bbox, spec, size=46, dims =19, coords=None, buffer=1):
	(zoom, targ, (x0, y0), (dx, dy)) = spec
	canvas = np.zeros((size, size, dims))

	shrink = size / 368
	xS, yS, xF, yF = bbox

	xS = int((dx + (xS - x0) / zoom) * shrink)
	yS = int((dy + (yS - y0) / zoom) * shrink)

	xF = int((dx + (xF - x0) / zoom) * shrink)
	yF = int((dy + (yF - y0) / zoom) * shrink)

	# print(spec)
	# print(xS, xF, yS, yF)
	# assert False
	for ii in range(dims):
		# canvas[y0:yF, x0:xF, ii] = 1
		canvas[max(yS-buffer, 0):yF+buffer, max(xS-buffer, 0):xF+buffer, ii] = 1

	if coords is not None:
		# zero out joints that are missing from PENN via masking
		for ii, joint in enumerate(coords):
			if joint is None:
				canvas[:, :, ii] = 0

	# canvas[:, :, -1] = 0 # ignore final by masking it out

	return canvas

def next_video_batch(refs, bsize=6):
	brefs = refs[0][:bsize]
	refs[0] = refs[0][bsize:]

	if len(refs[0]) < bsize:
		shuffed = refs[1]
		shuffle(shuffed)
		refs[0] = shuffed

	videos = []
	masks = []
	targets = []

	for ref in brefs:
		sized, specs = zip(*[size_image(imread(path), ref['boxes'][ii]) for ii, path in enumerate(ref['frames'])])

		heats = [create_heatmaps(ref['coco_coords'][ii], specs[ii]) for ii in range(len(ref['frames']))]
		mask = [create_mask(ref['boxes'][ii], specs[ii], coords=ref['coco_coords'][ii]) for ii in range(len(ref['frames']))]

		# mask all except final
		for ii in range(len(ref['frames'])):
			# heats[ii][:, :, :-1] = np.multiply(heats[ii][:, :, :-1], mask[ii][:, :, :-1])
			heats[ii][:, :, :] = np.multiply(heats[ii][:, :, :], mask[ii][:, :, :])

		videos.append(sized)
		masks.append(mask)
		targets.append(heats)

	return (
		np.array(videos),
		np.array(masks),
		np.array(targets))




