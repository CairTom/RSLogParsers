import time, datetime
from RSApi import RSNGM20xPowerSupply

now = datetime.datetime.now()
out_csv = 'RS_NGM20x_Logger_%s.csv' % now.strftime("%Y_%m_%d_%H_%M_%S")
csv_fp = open(out_csv, "w")

csv_fp.write("UnixTime,StringTime,Ah,Wh,VAvg,IAvg,WAvg,NSamplesBlock,NSamplesTotal,EffSampleRate\n")

print("Saving output to %s" % out_csv)

psu = RSNGM20xPowerSupply('10.0.5.55', 5025)
psu.sync_datetime()

#print("Calculating zero...")
#psu.output_off_zero(1)

psu.set_output_param(1, 3.3, 0.1)
psu.output_enable(1, True)

def write_csv_line(fp, t, data):
	ut = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
	
	csv_fp.write("%.5f,%s," % (t, ut))
	csv_fp.write("%15.15f,%15.15f,%15.15f,%15.15f,%15.15f,%d,%d,%.3f\n" % tuple(data))
	
	print(data)
	csv_fp.flush()

while True:
	print("Iter")
	psu.start_logger_scpi('S250K')
	
	time.sleep(1.0)
	
	origin_time = time.time()
		
	while True:
		if psu.get_logger_data_availability(1):
			block = psu.read_logger_data()
			write_csv_line(csv_fp, time.time() - origin_time, psu.process_ah_block(1, block, 250000))
		
		#time.sleep(0.01)