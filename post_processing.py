import methods as ms
import cv2 as cv
import tifffile as tiffio
import sys

from tqdm import tqdm
import numpy as np

import matplotlib.pyplot as plt

#fname = 'SR005-T1-6'
#fname = 'SR005-CL2-4'
#hd_name = 'Expansion'
#zarr_number = 8

def print_help():
	print("This is a help for Seckler Post Processing Software.")
	print("It expects to accept the input from MUSE REVA Preprocessing Software.")
	print("Command: python post_processing.py <File Name> <Path to Data> <Fire Run> <Last Run> <Options>")
	print("")
	print("-bk <image number>	Skips to image listed, analyzes that image, and that stops program. Default 0th image")
	print("-bt			Preforms enhanced contrast enhancement using TopHat and BlackHat Imaging Modalities")
	print("-ct <factor> <mean>	Contrasts the data according to new_px = factor * (old_px - mean) + 2055. Default: Factor = 3 and Mean = Image Mean")
	print("-cp <height_min> <height_max> <width_min> <width_max>	Crops the image to the specified height and width. Default: Will not crop")
	print("-d <scale>		Downscale data by whatever factor the user inputs. Default: 5")
	print("-h:			Prints Help Message")
	print("-sb			Adds scalebar to images outputed")
	quit()


if sys.argv[1] == "-h":
	print_help()
fname = sys.argv[1]

base_path = sys.argv[2]
#base_path = '/media/james/' + sys.argv[2] + '/data/'


zarr_number_i = int(sys.argv[3])
zarr_number_f = int(sys.argv[4])

elipse_size = 30

contrast_factor = 3
nerve_factor = 0
#image_offset = 56
mean = 2055

crop_height = [0,-1]
crop_width = [0,-1]

sample = 50

down_scale = 5


downsample = False
scalebar = False
contrast = False
crop_image = False
black_hat_top_hat = False
stop_run = False
start_run = 0

#bar = cv.imread("./output/bar.png",cv.IMREAD_GRAYSCALE)
#bar = bar / 15
#bar = bar * 4095


difference = []

def inputparser():
	global downsample, scalebar, contrast, crop_image, black_hat_top_hat, stop_run
	global contrast_factor, nerve_factor, crop_height, crop_width, start_run, down_scale
	n = len(sys.argv)
	
	for i in range(n):
		tag = sys.argv[i]
		if tag[0] == "-":
			if tag == "-h":
				print_help()
			if tag == "-d":
				downsample = True
				try:
					down_scale = int(sys.argv[i+1])
				except:
					pass
			if tag == "-sb":
				scalebar = True
			if tag == "-ct":
				contrast = True
				try:
					contrast_factor = int(sys.argv[i+1])
					nerve_factor = int(sys.argv[i+2])
				except:
					pass
			if tag == "-cp":
				crop_image = True
				try:
					crop_height = [int(sys.argv[i+1]),int(sys.argv[i+2])]
					crop_width = [int(sys.argv[i+3]),int(sys.argv[i+4])]
				except:
					pass
			if tag == "-bt":
				black_hat_top_hat = True
			if tag == "-bk":
				stop_run = True
				try:
					start_run = int(sys.argv[i+1])
				except:
					pass


	

def calculate_mean_intensity(filelist):
	global errorlog
	counter = 0
	means = []
	for z in filelist:
		try:
			means, counter = load_image_and_get_mean_as_array(z,counter,means)
		except TypeError:#This is where we need to go in and make it revert to tiff stack
			errorlog.append(f"File {z} not found and it was skipped for processing")
	
	means = np.array(means)
	m = np.average(means)
	std = np.std(means)
	return m, std

def find_useable_images_and_reports_index(filelist,mean,std):
	global errorlog
	
	index = {}
	
	counter = 0
	
	threshhold = 4 * std
	
	zeros = 0
	
	for z in filelist:
		try:
			img, attrs = ms.get_image_from_zarr(z)
			for i in tqdm(range(len(img))):
				m = np.mean(img[i])
				if np.abs(mean-m) < threshhold and m > 0:
					index[counter] = {'file':z,'index':i,'run':get_run_from_index_number(z)}
				elif m > 0:
					cv.imwrite(f"./output/exclude_{i}.png",img[i]/16)
                    #Put in code in to track when images are bad as opposed to m == 0
#				elif m == 0:
#					zeros += 1
				counter += 1
		except TypeError:
			errorlog.append(f"File {z} not found and it was skipped for processing")
	
	return index

def load_image_and_get_mean_as_array(z,counter,means):
	img, attrs = ms.get_image_from_zarr(z)
	
	n = len(img)
	for i in range(n):
		if counter % sample == 0:
			mtemp = np.mean(img[i])
			if mtemp > 0:
				means.append(mtemp)
		counter += 1
	return means,counter

def get_run_from_index_number(z):
	run = z.split('.')[-2]
	return int(run.split('_')[-1])


def process_image(img,mean,radius,align_image=None):
	image = img - np.mean(img)
	img = img + mean

	size = np.amax(img.shape)
	img = ms.add_smaller_image_to_larger(img,size)
	crop,mask = ms.segment_out_the_nerve(img)
	
	x0 = int(crop[0])
	y0 = int(crop[1])
	
	image = ms.center_on_nerve(img,x0,y0)
	
	if radius > size:
		image = ms.add_smaller_image_to_larger(image,radius)
	else:
		image = ms.crop_down_to_size(image,radius)
	
	
	if align_image is None:
		print("Original,",x0,y0)
	else:
		image, s = ms.coregister(align_image,image)
	return image
		
		
def overlay_images(image1, image2):
	# Ensure both images have the same shape
	if image1.shape != image2.shape:
		raise ValueError("Both images must have the same dimensions.")
	
	# Create a copy of the second image to avoid modifying the original
	result_image = np.copy(image2)
	
	# Create a mask where image1 is not black (assuming grayscale images)
	mask = image1 > 0
	
	# Overlay image1 on top of image2 using the mask
	result_image[mask] = image1[mask]
	return result_image

def normalize_mean_and_enhance_contrast(img):
#	print(np.mean(img),mean)
	if nerve_factor > 0:
		zero = nerve_factor
	else:
		zero = np.mean(img)
	
	image = img - zero
	image = contrast_factor * image	
	image = image + mean
	
	# New intensity = contrast_factor * (Old intensity - 127) + 127
	
	image = np.clip(image,0,4095)
	return image

def img_processer(file_name,img_align,image_offset = 0):
	global difference
	img, attrs = ms.get_image_from_zarr(file_name)
	
	if img_align is None:
		img_align = img[0]
	n = int(img.shape[0] / 1)
	image = None
	
	counter = image_offset
	for i in tqdm(range(n)):
		pre_index = 1 * i - 1
		index = 1 * i + 0
		if np.sum(img[index]) > 0 and i >= start_run:
			image = img[index]

			image, shift= ms.coregister(img_align,image)
			
			img_align = ms.copy(image)
			
			if crop_image:
				image = image[crop_height[0]:crop_height[1],crop_width[0]:crop_width[1]]
			
			if contrast:
				image = normalize_mean_and_enhance_contrast(image)
#				image = ms.normalize_to_mean(image,mean)
			else:
				image = ms.normalize_to_mean(image,mean)
			
			if black_hat_top_hat:
				kernel = cv.getStructuringElement(cv.MORPH_ELLIPSE,(elipse_size,elipse_size))
				topHat = cv.morphologyEx(image, cv.MORPH_TOPHAT, kernel)
				blackHat = cv.morphologyEx(image, cv.MORPH_BLACKHAT, kernel)
				image = image + topHat - blackHat

			
			if scalebar:
				image = ms.add_scalebar_to_image(image,4095)
			
			if downsample:
				down_points = (int(image.shape[1] / down_scale), int(image.shape[0] / down_scale))
				image = cv.resize(image, down_points, interpolation= cv.INTER_LINEAR)
			
			if counter < 100:
				if counter < 10:
					c = '00' + str(counter)
				else:
					c = '0' + str(counter)
			else:
				c = str(counter)
			cv.imwrite("./output/" + fname + f"/image_{c}.png",image/16)
			counter += 1
			if stop_run:
				break
	return img_align, counter	

inputparser()

n = zarr_number_f - zarr_number_i + 1
img_to_align = None
c = 0

ms.replace_directory("./output/" + fname + "/")
for i in range(n):
	zarr_number = str(zarr_number_i + i)
	path = base_path + fname + '/MUSE_stitched_acq_'  + zarr_number + '.zarr'
	img_to_align, c = img_processer(path,img_to_align, c)
	if stop_run:
		break


