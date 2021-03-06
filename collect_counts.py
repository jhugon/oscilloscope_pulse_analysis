#!/usr/bin/env python3

from oscilloscope import *
import time
import numpy as np
import datetime
import h5py

import vxi11

def collect_counter_data(ip,out_file,trigger_values,time_per_trig_val):
    """
    out_file: open h5py file to write to
    trigger_values: a list of trigger levels (in millivolts) to collect counter data for
    time_per_trig_val: how long to count for each trigger value, in seconds
    """
    instr =  vxi11.Instrument(ip)
    idn = instr.ask("*IDN?")
    if not (MODEL in idn):
        raise Exception(f"Instrument at {ip} not a {MODEL}, it's a: {idn}")
    instr.write(":counter:enable on")
    instr.write(":counter:source channel1")
    instr.write(":counter:mode totalize") # frequency period totalize

    trigger_values_set_ds = out_file.create_dataset("trigger_values_set",data=trigger_values)
    trigger_values_set_ds.attrs["units"] = "mV"
    counts = out_file.create_dataset("counts",len(trigger_values))
    counts.attrs["time_interval"] = time_per_trig_val
    counts.attrs["time_interval_units"] = "s"
    trigger_values_ds = out_file.create_dataset("trigger_values",len(trigger_values))
    trigger_values_ds.attrs["units"] = "mV"
    for i, trig_val in enumerate(trigger_values):
        instr.write(":trigger:edge:level {:f}".format(trig_val*1e-3))
        time.sleep(0.1)
        trigger_val_readback = instr.ask(":trigger:edge:level?")
        trigger_val_readback = float(trigger_val_readback)*1e3
        time.sleep(0.1)
        instr.write(":counter:totalize:clear")
        time.sleep(time_per_trig_val)
        count = instr.ask(":counter:current?")
        counts[i] = count
        trigger_values_ds[i] = trigger_val_readback
        print("Count for set {} mV read {:.1f} mV trigger: {}".format(trig_val,trigger_val_readback,count))

def normal_counts(ip):
    now = datetime.datetime.now().replace(microsecond=0)
    setup_vert(ip,200e-3,-400e-3,probe=1,bwlimit="20M")
    setup_horiz(ip,100e-9,0)
    setup_trig(ip,100e-3,10e-6)
    time_per_trig_val = 1
    trig_max = 850
    trig_min = 350
    trig_n_vals = 20
    trigger_values = np.linspace(trig_min,trig_max,trig_n_vals)
    print(f"Spending {time_per_trig_val} s triggering on each of {trig_n_vals} values between {trig_min} and {trig_max} mV")
    out_file_name = "counts_{}_{:d}trigs_{:.0f}to{:.0f}mV_{:.0f}s.hdf5".format(now.isoformat(),trig_n_vals,trig_min,trig_max,time_per_trig_val)
    print(f"Output filename is: {out_file_name}")
    with h5py.File(out_file_name,"w") as out_file:
        collect_counter_data(ip,out_file,trigger_values,time_per_trig_val)

def max_resolution_counts(ip):
    """
    trigger must be a multiple of 8 mV
    """
    now = datetime.datetime.now().replace(microsecond=0)
    setup_vert(ip,200e-3,-400e-3,probe=1,bwlimit="20M")
    setup_horiz(ip,100e-9,0)
    setup_trig(ip,100e-3,10e-6)
    time_per_trig_val = 1
    trigger_values = np.arange(344,850,8)
    trig_max = trigger_values[-1]
    trig_min = trigger_values[0]
    trig_n_vals = len(trigger_values)
    print(f"Spending {time_per_trig_val} s triggering on each of {trig_n_vals} values between {trig_min} and {trig_max} mV")
    out_file_name = "counts_max_res_{}_{:d}trigs_{:.0f}to{:.0f}mV_{:.0f}s.hdf5".format(now.isoformat(),trig_n_vals,trig_min,trig_max,time_per_trig_val)
    print(f"Output filename is: {out_file_name}")
    with h5py.File(out_file_name,"w") as out_file:
        collect_counter_data(ip,out_file,trigger_values,time_per_trig_val)

def pulser_waveform_run(ip):
    channel="channel1"
    nWaveforms=10000
    now = datetime.datetime.now().replace(microsecond=0)
    setup_vert(ip,200e-3,-400e-3,probe=1,bwlimit="20M",channel=channel)
    setup_horiz(ip,50e-9,0)
    setup_trig(ip,200e-3,10e-6,sweep="single",channel=channel)

    print(f"Collecting {nWaveforms}")
    out_file_name = "waveforms_{}_{:d}waveforms.hdf5".format(now.isoformat(),nWaveforms)
    print(f"Output filename is: {out_file_name}")
    collect_waveforms(ip,out_file_name,nWaveforms,source=channel)

if __name__ == "__main__":
    ip = "192.168.55.2"
    #normal_counts(ip)
    max_resolution_counts(ip)
