#!/usr/bin/env python

import sys
import os
import yaml
import numpy as np
import numpy.linalg
import glob
import cv2
import pprint
import csv

import cv_bridge
import rosbag
import sensor_msgs
import sensor_msgs.msg

global Kr
global Kd
global p_world
global I_depth
global coords

def calibrate():

    global Kr
    global Kd
    global p_world
    global I_depth
    global coords

    # convert to numpy array
    x = np.array(coords)

    # homogeneous coordinates
    x_tilde = np.hstack((x, np.ones((len(x), 1))))

    # extract calibration depth matrix
    K = np.array(Kd['camera_matrix']['data']).reshape(3, 3)

    # transformed
    Xc = np.dot(np.linalg.inv(K), x_tilde.T)

    # extract depth
    s = np.array([I_depth[c[1], c[0]] for c in coords])

    # scale 
    X = np.multiply(Xc, np.tile(s / 1000., (3, 1)))

    # transorm to x : out, y : left, z : up
    R = np.array([
        [0.0,   0.0,    1.0],
        [-1.0,  0.0,    0.0],
        [0.0,   -1.0,   0.0]])
    p_camera = np.dot(R, X).T

    # build A matrix
    dim = len(p_camera)
    A = np.zeros((3*dim, 12))
    for i in range(0, dim):
        A[3*i,      0]  = p_camera[i, 0]
        A[3*i,      1]  = p_camera[i, 1]
        A[3*i,      2]  = p_camera[i, 2]
        A[3*i,      9]  = 1
        A[3*i + 1,  3]  = p_camera[i, 0]
        A[3*i + 1,  4]  = p_camera[i, 1]
        A[3*i + 1,  5]  = p_camera[i, 2]
        A[3*i + 1,  10] = 1
        A[3*i + 2,  6]  = p_camera[i, 0]
        A[3*i + 2,  7]  = p_camera[i, 1]
        A[3*i + 2,  8]  = p_camera[i, 2]
        A[3*i + 2,  11] = 1

    # build b
    b = np.reshape(p_world, 3*dim)

    # least squares
    x, r, rank, s = np.linalg.lstsq(A, b)

    # extract elements from x
    R = np.array([x[:3], x[3:6], x[6:9]])
    t = x[9:]

    # set singular values to one to make R orthogonal
    U, S, V = np.linalg.svd(R)
    R = np.dot(U, V)

    return R, t

def load_images(f):

    # bag file 
    bag = rosbag.Bag(f, 'r')

    # cv bridge object
    bridge = cv_bridge.CvBridge()

    # extract rgb image
    msg = sensor_msgs.msg.Image()
    for topic, msg, t in bag.read_messages(topics='/camera/rgb/image_raw'):
        pass

    I_rgb = bridge.imgmsg_to_cv2(msg, desired_encoding="bgr8")

    # extract depth image
    msg = sensor_msgs.msg.Image()
    for topic, msg, t in bag.read_messages(topics='/camera/depth/image_raw'):
        pass

    I_depth = bridge.imgmsg_to_cv2(msg, desired_encoding="16UC1")

    return I_rgb, I_depth

def load_ground_truth(f):

    gt = []
    with open(f, 'r') as fstream:

        # for each line
        for line in fstream:

            # clean the junk
            cleanline = line.replace('\n', '').replace(' ', '')

            # parse
            gt.append(cleanline.split(','))

    # cast to numpy array
    gt = np.array(gt, dtype=np.float64)

    # remove id
    gt = gt[:, 1:]

    return np.array(gt)

def load_intrinsics(f):

    # parse
    calib = {}
    with open(f, 'r') as fstream:
        try:
            calib = yaml.load(fstream)
        except yaml.YAMLError as exception:
            print exception

    return calib

def mouse_callback(event, x, y, flags, param):

    global coords
    global p_world

    if event == cv2.EVENT_FLAG_LBUTTON:

        # append to list of points
        coords.append([x, y])

        # if we have enough points calibrate
        if (len(coords) == len(p_world)):

            R, t = calibrate()

            # print
            print('Rotation:')
            print(R)
            print('Translation:')
            print(t)

            coords = []



if __name__ == '__main__':

    if len(sys.argv) < 5:
        print 'Usage: ' + os.path.basename(sys.argv[0]) + \
                ' <rgb_calibration.yaml>' + ' <depth_calibration.yaml>' + \
                ' <ground_truth.txt>' + ' <bag_file.bag>'
        sys.exit()

    global Kr
    global Kd
    global p_world
    global I_depth
    global coords

    # intrinsic calibrations
    Kr = load_intrinsics(sys.argv[1])
    Kd = load_intrinsics(sys.argv[2])

    # load ground truth
    p_world = load_ground_truth(sys.argv[3])

    # load the images from the bag file
    [I_rgb, I_depth] = load_images(sys.argv[4])

    # correct for distortion
    I_rgb = cv2.undistort(I_rgb,
            np.array(Kr['camera_matrix']['data']).reshape(3, 3),
            np.array(Kr['distortion_coefficients']['data']))
    I_depth = cv2.undistort(I_depth,
            np.array(Kd['camera_matrix']['data']).reshape(3, 3),
            np.array(Kd['distortion_coefficients']['data']))

    # init camera points
    coords = []

    # click and do stuff
    cv2.namedWindow('image')
    cv2.setMouseCallback('image', mouse_callback)
    cv2.imshow('image', I_rgb)
    cv2.waitKey(0)



