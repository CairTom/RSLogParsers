"""
Reads R&S Raw FastLOG format for NGM20x power supply (single channel assumed)
and produces uAh and windowed charge data.

Call as:
   python RSLogParse.py <basefile> <window_period_s> <offset_ua>
  
Example:
   python RSLogParse.py flog-20200901T140613-ch1 0.001 30
   
   uses flog-20200901T140613-ch1.raw as the data file and flog-20200901T140613-ch1.meta as
   the description file, and uses a windowing period of 1ms for the windowed Ah measurement,
   and subtracts 30uA from all current measurements before accumulating them.
   
   Windowing period should be a multiple of sample rate to ensure accurate measurement.
   
   output file is flog-20200901T140613-ch1_processed.csv

"""

import sys, struct, os

def _fixedpoint15(v):
	# Display femto-amphours figure as fixed point decimal
	if (v < 0):
		s = -1
		div = (-v) / 1e15
		dec = (-v) % 1e15
		res = ("-%d.%015d") % (div, dec)
	else:
		s = +1
		div = v / 1e15
		dec = v % 1e15
		res = ("+%d.%015d") % (div, dec)
	
	#print(v, s, res)
	
	return res

if sys.version_info[0] != 3:
	raise RuntimeError("You need Python 3")

base_name = sys.argv[1]

raw_file = base_name + ".raw"
meta_file = base_name + ".meta"
out_file = base_name + "_processed.csv"

raw_fp = open(raw_file, "rb")
meta_fp = open(meta_file, "r")	
out_fp = open(out_file, "w")

samples = os.stat(raw_file).st_size / 8

window_time = float(sys.argv[2])
offset_ua = int(sys.argv[3])

# Find the sampling rate
sample_rate = None

for line in meta_fp.readlines():
	l = line.strip()
	
	if l.startswith("Samplerate"):
		sample_rate = float(l.split("\t")[1].strip())
	
if sample_rate == None:
	raise RuntimeError("Unable to find Samplerate parameter in .meta file")

sample_scale = (1e15 * (1.0 / sample_rate)) / 3600  # Scale factor for 1A in femto-amphours for the sample window
sample_sub_window = sample_rate * window_time

if abs(int(sample_sub_window) - sample_sub_window) > 0.000001:
	print("WARNING:  subsampled window might not be a multiple of the sample window, please check")

print("Using sample rate:    %.3f" % sample_rate)
print("Using sample scale:   %d" % sample_scale)
print("Using current offset: %d uA" % offset_ua)
print("")

out_fp.write("Nsamp,Nsubsamp,Ah_total,Wh_total,Ah_window,Wh_window,I,V,W\n")

# Process each 8 bytes of data file.  Parameters are voltage and current in IEEE754 format, little endian.
# Read 512 bytes at a time to maximise read/process rate.
parser = struct.Struct("<ff")

# Accumulated figures in femto amphours (unlimited maximum integer)
ah_total = 0
wh_total = 0
ah_start = 0
wh_start = 0
ah_sub = 0
wh_sub = 0
nsamp = 0
nsubsamp = 0

while True:
	data = raw_fp.read(512)
	
	if len(data) == 0:
		break
	
	for blk in range(int(len(data) / 8)):
		#print(blk)
		
		v, i = parser.unpack_from(data, blk * 8)
		i -= offset_ua * 1e-6
		#print(v, i)
		
		w = v * i
		ah_total += int(int(int(i * 1e6) * sample_scale) / 1e6)
		wh_total += int(int(int(w * 1e6) * sample_scale) / 1e6)
		nsamp += 1
		nsubsamp += 1
		
		if nsubsamp >= sample_sub_window:
			ah_sub = ah_total - ah_start
			wh_sub = wh_total - wh_start
			ah_start = ah_total
			wh_start = wh_total
		
			outstr  = "%d,%d," % (nsamp, nsubsamp)
			outstr += _fixedpoint15(ah_total) + ","
			outstr += _fixedpoint15(wh_total) + ","
			outstr += _fixedpoint15(ah_sub) + ","
			outstr += _fixedpoint15(wh_sub) + ","
			outstr += "%f,%f,%f\n" % (i, v, w)
			#print(outstr)
			out_fp.write(outstr)
			
			nsubsamp = 0
		
	if (nsamp % 65536) == 0:
		print("%10d/%10d  %4.3f%%" % (nsamp, samples, (nsamp * 100) / samples))
		
print(ah_total)
print(ah_total / 1e15)

out_fp.close()

	