#!/usr/bin/python3

# ****************************************************************************
# Copyright(c) 2017 Intel Corporation. 
# License: MIT See LICENSE file in root directory.
# ****************************************************************************

# How to classify images using DNNs on Intel Neural Compute Stick (NCS)

import mvnc.mvncapi as mvnc
import numpy
import datetime
import os
import sys
import cv2
from picamera import PiCamera
from picamera.array import PiRGBArray
from scipy.misc import imrotate
from functools import partial
import time
import io

# User modifiable input parameters
HOME_PATH               = '/home/pi/occupancy_detection'
GRAPH_PATH              = HOME_PATH + '/data/graph' 
IMAGE_DIM               = ( 227, 227 )
ilsvrc_mean = numpy.load(HOME_PATH + '/data/image_mean.npy').mean(1).mean(1) #loading the mean file

def crop_image(img):
    img = imrotate(img, -4.5) 
    img = img[ 592 : 1243 + 592, 736: 2354 + 736]
    cv2.imwrite("cropped_img.png", img)

    return img

def split_to_five(img):
    height, width, channels = img.shape

    top_left = img[0:height//2, 0:width//2]
    top_right = img[0:height//2, width//2 : width]

    bottom_left = img[height//2: height-1, 0:width//2]
    bottom_right = img[height//2: height-1, width//2: width]

    center_factor = 104

    center = img[height//4:3*height//4-1, width//4 - center_factor : 3*width//4 - center_factor] 

    split_images = [top_left, top_right, bottom_left, bottom_right, center]
    cv2.imwrite("top_left.png", top_left)
    cv2.imwrite("top_right.png", top_right)
    cv2.imwrite("bottom_left.png", bottom_left)
    cv2.imwrite("bottom_right.png", bottom_right)
    cv2.imwrite("center.png", center)

    split_images = list(map(transform_img, split_images))
    return split_images

def transform_img(img, img_width=IMAGE_DIM[0], img_height=IMAGE_DIM[1]):

    #Histogram Equalization
    img[:, :, 0] = cv2.equalizeHist(img[:, :, 0])
    img[:, :, 1] = cv2.equalizeHist(img[:, :, 1])
    img[:, :, 2] = cv2.equalizeHist(img[:, :, 2])

    #Image Resizing
    old_size = img.shape[:2]
    desired_size = img_width
    ratio = float(desired_size)/max(old_size)
    new_size = tuple([int(x*ratio) for x in old_size])

    img = cv2.resize(img, (new_size[1], new_size[0]), interpolation = cv2.INTER_CUBIC)

    delta_w = desired_size - new_size[1]
    delta_h = desired_size - new_size[0]
    top, bottom = delta_h//2, delta_h - (delta_h//2)
    left, right = delta_w//2, delta_w - (delta_w//2)
    color = [0,0,0]

    new_img = cv2.copyMakeBorder(img, top, bottom, left, right, cv2.BORDER_CONSTANT, value=color)
    return new_img

def normalize_img(img):
    img=cv2.resize(img,IMAGE_DIM)
    img = img.astype(numpy.float32)
    img[:,:,0] = (img[:,:,0] - ilsvrc_mean[0])
    img[:,:,1] = (img[:,:,1] - ilsvrc_mean[1])
    img[:,:,2] = (img[:,:,2] - ilsvrc_mean[2])
    cv2.imwrite("normalized_img.png", img)
    return img

def predict_occupancy(graph,img):
    # Load the image as a half-precision floating point array
    graph.LoadTensor( img.astype( numpy.float16), 'user object' )

    # ---- Step 4: Read & print inference results from the NCS -------------------

    # Get the results from NCS
    output, userobj = graph.GetResult()

    return numpy.argmax(output)

# ---- Step 1: Open the enumerated device and get a handle to it -------------

# Look for enumerated NCS device(s); quit program if none found.
devices = mvnc.EnumerateDevices()
if len( devices ) == 0:
	print( 'No devices found' )
	quit()

# Get a handle to the first enumerated device and open it
device = mvnc.Device( devices[0] )
device.OpenDevice()

# ---- Step 2: Load a graph file onto the NCS device -------------------------

# Read the graph file into a buffer
with open( GRAPH_PATH, mode='rb' ) as f:
	blob = f.read()

# Load the graph buffer into the NCS
graph = device.AllocateGraph( blob )

camera = PiCamera()
time.sleep(0.2)
#stream = PiRGBArray(camera)
stream = io.BytesIO()
camera.resolution = (3280, 2464)


now = datetime.datetime.now()
today10pm = now.replace(hour = 22, minute=0, second=0,microsecond=0)
lastCaptured = now
captureRate = 15

while(True):
    timestamp = datetime.datetime.now()
    if timestamp > today10pm:
        sys.exit(0)
    if (timestamp - lastCaptured).seconds >= captureRate:
        lastCapured = timestamp
        print("CAPTURING IMAGE: ")
        camera.capture(stream, format="jpeg")
        data = numpy.fromstring(stream.getvalue(),dtype=numpy.uint8)
        image = cv2.imdecode(data,1)

        image = crop_image(image)

        divided_images = split_to_five(image)
        
        normalized_images = list(map(normalize_img, divided_images))
        
        room_vector = list(map(partial(predict_occupancy,graph), normalized_images))

        print("Room vector {}".format(room_vector))

        stream.truncate(0)
        stream.seek(0)

graph.DeallocateGraph()
device.CloseDevice()


