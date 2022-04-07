#!/usr/bin/env python3

from oscilloscope import *
from waveform_analysis import *
import numpy as np
import time
import datetime
import h5py
from hist import Hist
import matplotlib.pyplot as mpl
import matplotlib.colors
from scipy import signal
from scipy import interpolate

import vxi11

def collect_step_response_data(ip,verts_in,verts_sig_gen,nWaveforms,in_channel="channel1",sig_gen_channel="1",horiz=(500e-9,0),trigger_thresholds=None):
    """
    Generates a square waveform and records the resulting input waveforms.
    """
    now = datetime.datetime.now().replace(microsecond=0)
    setup_horiz(ip,*horiz)

    print(f"Collecting {nWaveforms}")
    out_file_name = "step_response_{}_{:d}waveforms.hdf5".format(now.isoformat(),nWaveforms)
    print(f"Output filename is: {out_file_name}")

    if trigger_thresholds is None:
        trigger_thresholds = np.zeros(len(verts_in))

    with h5py.File(out_file_name,"w") as out_file:
        step_response_grp = out_file.create_group("step_response")
        for iVert,(vert_in,vert_sig_gen,trigger_threshold) in enumerate(zip(verts_in,verts_sig_gen,trigger_thresholds)):
            amp_group = step_response_grp.create_group(f"sig_gen_setting{iVert}")
            amp_group.attrs["amplitude"] = vert_in[0]
            amp_group.attrs["offset"] = vert_in[1]
            amp_group.attrs["amplitude_units"] = "V"
            amp_group.attrs["offset_units"] = "V"
            setup_vert(ip,vert_in[0],vert_in[1],probe=1,channel=in_channel)
            setup_trig(ip,trigger_threshold,10e-6,sweep="single",channel=in_channel)
            setup_sig_gen(ip,sig_gen_channel,"square",vert_sig_gen[0],vert_sig_gen[1],2e5,out50Ohm=True)
            time.sleep(0.5)
            collect_waveforms(ip,amp_group,nWaveforms,channel=in_channel)

    return out_file_name

def collect_positive_step_response_data(ip,amplitudes_sig_gen,nWaveforms,gain=10.,in_channel="channel1",sig_gen_channel="1",horiz=(500e-9,0)):
    verts_sig_gen = [(x,0.5*x) for x in amplitudes_sig_gen]
    scale_in = find_smallest_setting(np.array(amplitudes_sig_gen)*1.1/4.)
    verts_in = [(x*gain,-0.5*y*gain) for x,y in zip(scale_in,amplitudes_sig_gen)]
    trigger_thresholds = [0.5*x*gain for x in amplitudes_sig_gen]
    return collect_step_response_data(ip,verts_in,verts_sig_gen,nWaveforms,in_channel=in_channel,sig_gen_channel=sig_gen_channel,horiz=horiz,trigger_thresholds=trigger_thresholds)


def collect_bipolar_step_response_data(ip,amplitudes_sig_gen,nWaveforms,gain=10.,in_channel="channel1",sig_gen_channel="1",horiz=(500e-9,0)):
    verts_sig_gen = [(2*x,0.) for x in amplitudes_sig_gen]
    scale_in = find_smallest_setting(np.array(amplitudes_sig_gen)*1.1/4.)
    verts_in = [(x*gain,0.) for x in scale_in]
    return collect_step_response_data(ip,verts_in,verts_sig_gen,nWaveforms,in_channel=in_channel,sig_gen_channel=sig_gen_channel,horiz=horiz)

def find_waveform_bottom_top(waveform_hist):
        v_hist_array = waveform_hist[0:len:sum,:].values() # gets rid of over/underflow
        v_hist_array_max = max(v_hist_array)
        peak_indices, peak_props = signal.find_peaks(v_hist_array,height=v_hist_array_max*0.2)
        peak_heights = peak_props["peak_heights"]
        peak_widths = signal.peak_widths(v_hist_array,peak_indices)[0]
        results = []
        if len(peak_indices) == 2:
            for iPeak in range(len(peak_indices)):
                peak_index = peak_indices[iPeak]
                peak_width = peak_widths[iPeak]
                peak_hist = waveform_hist.project("voltage")[int(peak_index-2*peak_width):int(np.ceil(peak_index+2*peak_width))]
                peak_mean = np.average(peak_hist.axes[0].centers,weights=peak_hist.values())
                results.append(peak_mean)
        else:
            return [None,None]
        return results

def find_step_times(profile,bottom,mid,top):
    # clip 10% on either end
    nBinsOrig = profile.size
    profile = profile[int(0.1*nBinsOrig):int(0.9*nBinsOrig)]
    Vpp = top-bottom
    V1pct = Vpp*0.01+bottom
    V10pct = Vpp*0.1+bottom
    V90pct = Vpp*0.9+bottom
    V99pct = Vpp*0.99+bottom
    tMid = profile.axes[0].centers[profile.values() >= mid][0]
    profile_before_mid = profile[:tMid*1j]
    profile_after_mid = profile[tMid*1j:]
    t1pct = profile_before_mid.axes[0].centers[profile_before_mid.values() <= V1pct][-1]
    t10pct = profile_before_mid.axes[0].centers[profile_before_mid.values() <= V10pct][-1]
    t90pct = profile_after_mid.axes[0].centers[profile_after_mid.values() >= V90pct][0]
    t99pct = profile_after_mid.axes[0].centers[profile_after_mid.values() >= V99pct][0]
    tSettle1pct = profile_after_mid.axes[0].centers[abs(profile_after_mid.values()-top)/(top-bottom) > 0.01][-1]
    tSettle0p1pct = profile_after_mid.axes[0].centers[abs(profile_after_mid.values()-top)/(top-bottom) > 0.005][-1]
    return tMid, t1pct, t10pct, t90pct, t99pct, tSettle1pct, tSettle0p1pct

def analyze_step_waveform_dset(waveform_dset,sig_gen_Vpp):

        caption = f"Sig-Gen Vpp = {sig_gen_Vpp}"
        waveform_hist = make_hist_waveformVtime(waveform_dset,time_units="ns",voltage_units="mV",downsample_time_by=10)
        waveform_hist = waveform_hist[-200j:1000j,:][0:len,0:len] # second slice gets rid of overflow
        waveform_profile = waveform_hist.profile("voltage")
        bottom,top = find_waveform_bottom_top(waveform_hist)
        Vmax = max(waveform_profile.values())
        Vmin = min(waveform_profile.values())
        Vpp = float('nan')
        mid = float('nan')
        overshoot = float('nan')
        undershoot = float('nan')
        tMid, t1pct, t10pct, t90pct, t99pct, tSettle1pct, tSettle0p1pct = [float('nan')]*7
        try:
            overshoot = (Vmax-top)/Vpp
            mid = (top+bottom)/2.
            undershoot = (bottom-Vmin)/Vpp
            Vpp = top-bottom
        except TypeError:
            Vpp = float('nan')
            mid = float('nan')
            overshoot = float('nan')
            undershoot = float('nan')
        else:
            tMid, t1pct, t10pct, t90pct, t99pct, tSettle1pct, tSettle0p1pct = find_step_times(waveform_profile,bottom,mid,top)

        statistics = {
            "top": top,
            "bottom": bottom,
            "mid" : mid,
            "Vpp" : Vpp,
            "max" : Vmax,
            "min" : Vmin,
            "overshoot": overshoot,
            "undershoot": undershoot,
            "tMid": tMid,
            "t1pct": t1pct,
            "t10pct": t10pct,
            "t90pct": t90pct,
            "t99pct": t99pct,
            "tSettle1pct": tSettle1pct,
            "tSettle0p1pct" : tSettle0p1pct,
            "risetime10-90" : t90pct-t10pct,
            "risetime1-99" : t99pct-t1pct,
        }

        fig, ax = mpl.subplots(figsize=(6,6),constrained_layout=False)
        waveform_hist.plot2d(ax=ax,norm=PHOSPHOR_HIST_NORM)
        #ax.axvline(t10pct,c="0.5")
        #ax.axvline(t90pct,c="0.5")
        #ax.axvline(tSettle1pct,c="0")
        #ax.axvline(tSettle0p1pct,c="0")
        #ax.axhline(bottom,c="0.5")
        #ax.axhline(top,c="0.5")
        waveform_profile.plot(ax=ax,color="r")
        #ax.set_xlim(t1pct-1*(t99pct-t1pct),t99pct+5*(t99pct-t1pct))
        #ax.set_ylim(Vmin-0.1*Vpp,Vmax+0.1*Vpp)
        fig.suptitle(caption)
        fig.savefig(f"step_response_waveform_{sig_gen_Vpp}.png")
        return statistics


def analyze_step_response_data(fn):

    with h5py.File(fn) as f:
        sr_dir = f["step_response"]
        sig_gen_Vpp_values = []
        stats = []
        for sgs_key in sr_dir:
            sgs_dir = sr_dir[sgs_key]
            sig_gen_Vpp = sgs_dir.attrs["amplitude"]
            sig_gen_Vpp_values.append(sig_gen_Vpp)
            stat = analyze_step_waveform_dset(sgs_dir["waveforms_raw"],sig_gen_Vpp)
            stats.append(stat)
        fig, ax = mpl.subplots(figsize=(6,6),constrained_layout=True)
        ax.plot(sig_gen_Vpp_values,[x["Vpp"] for x in stats])
        ax.set_xlabel("Signal Generator Amplitude [V]")
        ax.set_ylabel("V$_{pp}$ [V]")
        fig.savefig("step_response_Vpp.png")
        fig, ax = mpl.subplots(figsize=(6,6),constrained_layout=True)
        ax.plot(sig_gen_Vpp_values,[x["risetime1-99"] for x in stats],label="1%-99%")
        ax.plot(sig_gen_Vpp_values,[x["risetime10-90"] for x in stats],label="10%-90%")
        ax.set_xlabel("Signal Generator Amplitude [V]")
        ax.set_ylabel("Rise Time [s]")
        fig.savefig("step_response_rise_time.png")
 

def collect_noise_data(ip,nWaveforms,trigger_level=0,in_channel="channel1"):
    """
    Collects noise data assuming input port is appropriately terminated.
    """
    now = datetime.datetime.now().replace(microsecond=0)

    print(f"Collecting {nWaveforms}")
    out_file_name = "noise_{}_{:d}waveforms.hdf5".format(now.isoformat(),nWaveforms)
    print(f"Output filename is: {out_file_name}")

    setup_horiz(ip,1e-6,0)
    setup_vert(ip,1e-3,0,probe=1,channel=in_channel)
    setup_trig(ip,trigger_level,10e-6,sweep="single",channel=in_channel)
    time.sleep(0.5)

    with h5py.File(out_file_name,"w") as out_file:
        noise_grp = out_file.create_group("noise")
        collect_waveforms(ip,noise_grp,nWaveforms,channel=in_channel)

    return out_file_name


def analyze_noise_data(fn):
    with h5py.File(fn) as f:
        noise_dir = f["noise"]
        waveform_dset = noise_dir["waveforms_raw"]
        waveform_ffts, fft_freqs = fft_waveforms(waveform_dset)
        mean_fft_amp = np.sum(abs(waveform_ffts),axis=0)/waveform_ffts.shape[0]
        fig, ax = mpl.subplots(figsize=(6,6),constrained_layout=True)
        ax.loglog(fft_freqs,mean_fft_amp)
        ax.set_xlabel("Frequency [Hz]")
        ax.set_ylabel("Noise Amplitude [V]")
        ax.set_title("Noise Amplitude Spectrum")
        fig.savefig("Noise_spectrum.png")
        waveforms = calibrate_waveforms(waveform_dset)
        dataset_std = np.std(waveforms)
        print(f"Dataset Standard Deviation: {dataset_std*1e6:.1f} μV")


if __name__ == "__main__":
    ip = "192.168.55.2"
    ##fn = collect_positive_step_response_data(ip,[0.01,0.03,0.05,0.1,0.3],100,gain=10.)
    fn = "step_response_2022-04-07T15:16:35_100waveforms.hdf5"
    analyze_step_response_data(fn)
    #fn = collect_noise_data(ip,100,trigger_level=800e-6)
    fn = "noise_2022-04-07T15:38:08_100waveforms.hdf5"
    analyze_noise_data(fn)
