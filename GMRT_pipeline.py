# -*- coding: utf-8 -*-
# GMRT pipeline to be run in CASA (casa --nologger --nogui --log2term) with exec_file()

# Prepare fits file:
# ~/scripts/GMRTpipeline/listscan-1.bin 24_017-02may-dual.lta
# Edit log (dual: RR->610, LL->230) - set output name and 
# remove unused antennas to reduce the file size
# ~/scripts/GMRTpipeline/gvfits-1.bin 24_017-02may-dual.log

# example of config file (GMRT_pipeline_conf.py) which must be in the working dir:
#dataf = '180101.ms'
#flagf = ''
# format: dict of dicts, each dict has values for a target
# Mandatory fields are: flux_cal, gain_cal, target (all in format: ['fields','scans'])
# Facoltative fields are:
# mask (region, an initial mask for first cleaning),
# sub (region, region where to subtract hi-res model before low-res image),
# peel (list of regions, one for each source to peel),
# fmodel (model for flux cal in case CASA default is not good)
# mask_faint (region, with all faint sources that may be missed by source finder in making masks)
# extended (pybdsm atrous? default:False)
# multiscale (array of multiscales. default=[])
# threshold = 50e-6 # expected final noise in Jy
#obs={'A2142':{'flux_cal':['0',''],'gain_cal':['1',''],'target':['2','']},\
#'A2244':{'flux_cal':['0',''],'gain_cal':['3',''],'target':['4','']},\
#'A2589':{'flux_cal':['7',''],'gain_cal':['5',''],'target':['6','']}}
# format: {antenna:time,antenna:time...} or {} for none
#badranges = {'26':'2010/05/08/06:23:07~2010/05/08/06:31:15,2010/05/07/18:57:29~2010/05/07/18:58:21'}
# resolution -> 610: 1arcsec, 1400: 0.5arcsec
#sou_res = ['1arcsec']
# size -> 610: 5k, 1400: 4k
#sou_size = [5000]
# robust
#rob=0.5
# taper final image
#taper = '25arcsec'
# pipeline dir
#pipdir = '/home/stsf309/GMRTpipeline'

import os, sys, glob
import itertools
import datetime
import numpy as np
execfile('GMRT_pipeline_conf.py')
execfile(pipdir+'/GMRT_pipeline_lib.py')
execfile(pipdir+'/GMRT_peeling.py')
set_logger()

active_ms = dataf.replace('fits', 'ms').replace('FITS','ms')

#######################################
# prepare env

def step_env():
    logging.info("### RESET ENVIRONMENT")

    check_rm('img')
    check_rm('cal')
    check_rm('plots')
    check_rm('peel')
    os.makedirs('img')
    os.makedirs('cal')
    os.makedirs('plots')   
    os.makedirs('peel')   

    
#######################################
# import & plots

def step_import():
    logging.info("### IMPORT FILE AND FIRST PLTOS")

    if not os.path.exists(active_ms):
        default('importgmrt')
        importgmrt(fitsfile=dataf, vis=active_ms)
        logging.info("Created " + active_ms + " measurementset.")
    else:
        logging.warning("MS already present, skip importing")
    
    # apply observation flags
    if flagf!='':
        gmrt_flag(active_ms, flagf)
    else:
        logging.warning("No flag pre-applied.")
    
    # Create listobs.txt for references
    check_rm('listobs.txt')
    default('listobs')
    listobs(vis=active_ms, verbose=True, listfile='listobs.txt')
    
    # plot ants
    default('plotants')
    plotants(vis=active_ms, figfile='plots/plotants.png')
    
    # plot elev
    default('plotms')
    plotms(vis=active_ms, xaxis='time', yaxis='elevation', selectdata=True, antenna='0&1;2&3',\
    	spw='0:31', coloraxis='field', plotfile='plots/el_vs_time.png', overwrite=True)

    
####################################### 
# set important variables

def step_setvars(active_ms):
    logging.info("### SET VARIABLES")

    # find number of channels
    tb.open(active_ms+'/SPECTRAL_WINDOW')
    n_chan = tb.getcol('NUM_CHAN')
    freq = np.mean(tb.getcol('REF_FREQUENCY'))
    tb.close()
    if len(n_chan) == 1: assert(n_chan[0] == 512 or n_chan[0] == 256 or n_chan[0] == 128) 
    if len(n_chan) == 2: assert(n_chan[0] == 128 and n_chan[1] == 128)
    
    # get min baselines for calib
    tb.open( '%s/ANTENNA' % active_ms)
    nameAntenna = tb.getcol( 'NAME' )
    numAntenna = len(nameAntenna)
    tb.close()
    minBL_for_cal = max(3,int(numAntenna/4.0))

    # collect all sourcesnames and data
    sources = []
    for name, data in obs.items():
        sources.append(Source(name, data))

    return freq, minBL_for_cal, sources, n_chan

 
#######################################
# Pre-flag: remove first chan, quack, bad ant and bad time
    
def step_preflag(active_ms, freq, n_chan):
    logging.info("### FIRST FLAGGING")
    
    # report initial statistics
    statsFlag(active_ms, note='Initial')
    
    if len(n_chan) == 1 and n_chan[0] == 512:
        spw='0:0'
        if freq > 200e6 and freq < 300e6: spw='0:0~130' # 235 MHz +20 border
    elif len(n_chan) == 1 and n_chan[0] == 256:
        spw='0:0'
        if freq > 200e6 and freq < 300e6: spw='0:0~65' # 235 MHz +20 border
    elif len(n_chan) == 1 and n_chan[0] == 128:
        spw='0:0'
        if freq > 200e6 and freq < 300e6: spw='0:0~65' # 235 MHz +20 border
    elif len(n_chan) == 2 and n_chan[0] == 128 and n_chan[1] == 128:
        spw='0:0,1:0' # TODO: is also the chan 0 of the second spw to be flagged?
        if freq > 200e6 and freq < 300e6: spw='0:0~65,1:0' # 235 MHz +20 low border
    else:
        logging.error('Cannot understand obs type.')
        sys.exit(1)

    default('flagdata')
    flagdata(vis=active_ms, mode='manualflag', spw=spw, flagbackup=False)
    
    if badranges != {}:
        for badant in badranges:
            logging.debug("Flagging :"+badant+" - time: "+badranges[badant])
            default('flagdata')
            flagdata(vis=active_ms, mode='manualflag', antenna=badant,\
            	timerange=badranges[badant], flagbackup=False)
    
    # quack
    default('flagdata')
    flagdata(vis=active_ms, mode='quack', quackinterval=1, quackmode='beg', action='apply', flagbackup=False)
    
    # flag zeros
    default('flagdata')
    flagdata(vis=active_ms, mode='clip', clipzeros=True,\
    	correlation='ABS_ALL', action='apply', flagbackup=False)
    
    # save flag status
    default('flagmanager')
    flagmanager(vis=active_ms, mode='save', versionname='AfterStaticFlagging', comment=str(datetime.datetime.now()))

    # First RFI removal
    default('flagdata')
    statsFlag(active_ms, note='After static flagging, befor tfcrop.')
    flagdata(vis=active_ms, mode='tfcrop', datacolumn='data',
            timecutoff = 4., freqcutoff = 3., maxnpieces = 7,\
            action='apply', flagbackup=False)
    statsFlag(active_ms, note='End of initial flagging')

    # save flag status
    default('flagmanager')
    flagmanager(vis=active_ms, mode='save', versionname='AfterDynamicFlagging', comment=str(datetime.datetime.now()))
    
    
#######################################
# Set models
   
def step_setjy(active_ms): 
    logging.info("### SETJY")
    
    done = []
    for s in sources:
        if s.f in done: continue
        # check if there's a specific model
        if s.fmodel != '':
            logging.info("Using model "+s.fmodel+" for fux_cal "+s.f)
            default('ft')
            ft(vis=active_ms, field=s.f, complist=s.fmodel, usescratch=True)
        else:
            logging.info("Using default model for fux_cal "+s.f)
            default('setjy')
            setjy(vis=active_ms, field=s.f, standard='Perley-Butler 2010', usescratch=True, scalebychan=True)
        done.append(s.f)

    
#######################################
# Bandpass

def step_bandpass(active_ms, freq, n_chan, minBL_for_cal):    
    logging.info("### BANDPASS")
    
    done = []
    for s in sources:
        if s.f in done: continue

        check_rm('cal/flux_cal'+str(s.f))
        os.makedirs('cal/flux_cal'+str(s.f))
        check_rm('plots/flux_cal'+str(s.f))
        os.makedirs('plots/flux_cal'+str(s.f))

        if len(n_chan) == 1 and n_chan[0] == 512: initspw = '0:240~260'
        elif len(n_chan) == 1 and n_chan[0] == 256: initspw = '0:120~130'
        elif len(n_chan) == 1 and n_chan[0] == 128: initspw = '0:70~80'
        elif len(n_chan) == 2 and n_chan[0] == 128 and n_chan[1] == 128: initspw = '0:70~80, 1:70~80'

        for step in ['cycle1','final']:

            logging.info("Start bandpass step: "+step)

            gaintables=[]
            interp=[]
    
            refAntObj = RefAntHeuristics(vis=active_ms, field=s.f, geometry=True, flagging=True)
            refAnt = refAntObj.calculate()[0]

            if freq < 500e6:
                minsnr=3.0
            else:
                minsnr=5.0
        
            # gaincal on a narrow set of chan for BP and flagging
            #if step == 'cycle1': calmode='ap'
            #if step == 'final': calmode='p'

            logging.info("Phase calibration")
            default('gaincal')
            gaincal(vis=active_ms, caltable='cal/flux_cal'+str(s.f)+'/'+step+'-boot.Gp', field=s.f,\
            	selectdata=True, uvrange='>50m', scan=s.fscan, spw=initspw,\
                solint='int', combine='', refant=refAnt, minblperant=minBL_for_cal, minsnr=0, calmode='p')
            # smoothing solutions
            default('smoothcal')
            smoothcal(vis=active_ms, tablein='cal/flux_cal'+str(s.f)+'/'+step+'-boot.Gp', caltable='cal/flux_cal'+str(s.f)+'/'+step+'-boot.Gp-smooth')
            
            # init bandpass correction
            logging.info("Bandpass calibration 1")
            default('bandpass')
            bandpass(vis=active_ms, caltable='cal/flux_cal'+str(s.f)+'/'+step+'-boot.B', field=s.f, selectdata=True,\
            	uvrange='>100m', scan=s.fscan, solint='inf', combine='scan,field', refant=refAnt,\
            	minblperant=minBL_for_cal, minsnr=minsnr, solnorm=True, bandtype='B', gaintable=['cal/flux_cal'+str(s.f)+'/'+step+'-boot.Gp-smooth'], interp=['linear'])

            # find leftover time-dependent delays
            logging.info("BP: Delay calibration")
            default('gaincal')
            gaincal(vis=active_ms, caltable='cal/flux_cal'+str(s.f)+'/'+step+'.K', field=s.f, selectdata=True,\
                uvrange='>100m', scan=s.fscan, solint='int',combine='', refant=refAnt, interp=interp+['nearest,nearestflag'],\
                minblperant=minBL_for_cal, minsnr=minsnr,  gaintype='K', gaintable=gaintables+['cal/flux_cal'+str(s.f)+'/'+step+'-boot.B'])
            # flag outliers
            FlagCal('cal/flux_cal'+str(s.f)+'/'+step+'.K', sigma = 5, cycles = 3)
            # plot
            plotGainCal('cal/flux_cal'+str(s.f)+'/'+step+'.K', delay=True)
            gaintables.append('cal/flux_cal'+str(s.f)+'/'+step+'.K')
            interp.append('linear')

            # find time-dependant gains
            logging.info("BP: Gain calibration")
            default('gaincal')
            gaincal(vis=active_ms, caltable='cal/flux_cal'+str(s.f)+'/'+step+'.Gap', field=s.f, selectdata=True,\
                uvrange='>100m', scan=s.fscan, solint='int',combine='', refant=refAnt, interp=interp+['nearest,nearestflag'],\
                minblperant=minBL_for_cal, minsnr=minsnr,  gaintype='G', calmode='ap', gaintable=gaintables+['cal/flux_cal'+str(s.f)+'/'+step+'-boot.B'])
            # flag outliers
            FlagCal('cal/flux_cal'+str(s.f)+'/'+step+'.Gap', sigma = 3, cycles = 3)
            # plot
            plotGainCal('cal/flux_cal'+str(s.f)+'/'+step+'.Gap', amp=True, phase=True)
            gaintables.append('cal/flux_cal'+str(s.f)+'/'+step+'.Gap')
            interp.append('linear')

            # find cross-K
            logging.info("BP: Kcross calibration")
            default('gaincal')
            gaincal(vis=active_ms, caltable='cal/flux_cal'+str(s.f)+'/'+step+'.Kcross', field=s.f, selectdata=True,\
                uvrange='>100m', scan=s.fscan, solint='inf',combine='scan,field', refant=refAnt, interp=interp+['nearest,nearestflag'],\
                minblperant=minBL_for_cal, minsnr=minsnr,  gaintype='KCROSS', gaintable=gaintables+['cal/flux_cal'+str(s.f)+'/'+step+'-boot.B'])
            default('plotcal')
            # plot
            plotcal( caltable = 'cal/flux_cal'+str(s.f)+'/'+step+'.Kcross', xaxis = 'antenna', yaxis = 'delay', showgui=False, figfile= 'plots/flux_cal'+str(s.f)+'/'+step+'.Kcross.png' )
            gaintables.append('cal/flux_cal'+str(s.f)+'/'+step+'.Kcross')
            interp.append('nearest')

            # find leakage - doable only with full stokes!
#            logging.info("BP: Leakage calibration")
#            default('polcal')
#            polcal(vis=active_ms, caltable='cal/flux_cal'+str(s.f)+'/'+step+'.D', poltype = 'Df', preavg = 1., field=s.f, selectdata=True,\
#                uvrange='>100m', scan=s.fscan, solint='inf',combine='scan,field', refant=refAnt, interp=interp+['nearest,nearestflag'],\
#                minblperant=minBL_for_cal, minsnr=minsnr, gaintable=gaintables+['cal/flux_cal'+str(s.f)+'/'+step+'-boot.B'])
#            # plot
#            plotBPCal('cal/flux_cal'+str(s.f)+'/'+step+'.D', amp=True, phase=True)
#            gaintables.append('cal/flux_cal'+str(s.f)+'/'+step+'.D')
#            interp.append('nearest,nearestflag')

            # recalculate BP taking delays into account
            logging.info("Bandpass calibration 2")
            default('bandpass')
            bandpass(vis=active_ms, caltable='cal/flux_cal'+str(s.f)+'/'+step+'.B', field=s.f, selectdata=True,\
            	uvrange='>100m', scan=s.fscan, solint='inf', combine='scan,field', refant=refAnt, interp=interp,\
            	minblperant=minBL_for_cal, minsnr=minsnr, solnorm=True, bandtype='B', gaintable=gaintables)
            # plot
            plotBPCal('cal/flux_cal'+str(s.f)+'/'+step+'.B', amp=True, phase=True)
            gaintables.append('cal/flux_cal'+str(s.f)+'/'+step+'.B')
            interp.append('nearest,nearestflag')

            logging.info("Apply bandpass")
            default('applycal')
            applycal(vis=active_ms, selectdata=True, field=s.f, scan=s.fscan,\
            	gaintable=gaintables, calwt=False, flagbackup=False, interp=interp)
            
            if step != 'final':
                # clip on residuals
                clipresidual(active_ms, f=s.f, s=s.fscan)

        # end of 3 bandpass cycles
        done.append(s.f)
    # end of flux_cal cycles   

    # remove K, amp from gaintables, we keep B, Kcross and D which are global and T-indep
    gaintables=['cal/flux_cal'+str(s.f)+'/final.B', 'cal/flux_cal'+str(s.f)+'/final.Kcross']
    interp=['nearest,nearestflag','nearest,nearestflag']
    
    statsFlag(active_ms, note='Before apply bandpass')

    for s in sources:
        # apply bandpass to gain_cal
        default('applycal')
        applycal(vis=active_ms, selectdata=True, field=s.g, scan=s.gscan,\
            gaintable=gaintables, calwt=False, flagbackup=False, interp=interp)
        # apply bandpass to target
        default('applycal')
        applycal(vis=active_ms, selectdata=True, field=s.t, scan=s.tscan,\
            gaintable=gaintables, calwt=False, flagbackup=False, interp=interp)
        # fluxcal is already corrected (also with G and K, not a big deal)

    statsFlag(active_ms, note='After apply bandpass, before rflag')

    # run the final flagger
    default('flagdata')
    flagdata(vis=active_ms, mode='rflag',\
        ntime='scan', combinescans=False, datacolumn='corrected', winsize=3,\
        timedevscale=5, freqdevscale=5, action='apply', flagbackup=False)

    # flag statistics after flagging
    statsFlag(active_ms, note='After rflag')
 

#######################################
# Calib
    
def step_calib(active_ms, freq, minBL_for_cal):
    logging.info("### CALIB")
    
    for s in sources:

        check_rm('cal/'+s.name)
        os.makedirs('cal/'+s.name)
        check_rm('plots/'+s.name)
        os.makedirs('plots/'+s.name)

        n_cycles = 3
        for cycle in xrange(n_cycles):
    
            logging.info("Start CALIB cycle: "+str(cycle))
    
            refAntObj = RefAntHeuristics(vis=active_ms, field=s.f, geometry=True, flagging=True)
            refAnt = refAntObj.calculate()[0]
            
            gaintables=['cal/flux_cal'+str(s.f)+'/final.B', 'cal/flux_cal'+str(s.f)+'/final.Kcross']
            interp=['nearest,nearestflag','nearest,nearestflag']
    
            # Gain cal phase
            if freq < 500e6:
                minsnr=2.0
            else:
                minsnr=4.0
            default('gaincal')
            gaincal(vis=active_ms, caltable='cal/'+s.name+'/gain'+str(cycle)+'-boot.Gp', field=s.g+','+s.f, selectdata=True,\
            	uvrange='>100m', scan=",".join(filter(None, [s.fscan,s.gscan])), solint='int', refant=refAnt, interp=interp, \
                minblperant=minBL_for_cal, minsnr=minsnr, calmode='p', gaintable=gaintables)

            # find leftover time-dependent delays
            default('gaincal')
            gaincal(vis=active_ms, caltable='cal/'+s.name+'/gain'+str(cycle)+'.K', field=s.g+','+s.f, selectdata=True,\
                uvrange='>100m', scan=",".join(filter(None, [s.fscan,s.gscan])), solint='int', \
                refant=refAnt, minblperant=minBL_for_cal, minsnr=minsnr,  gaintype='K', interp=interp+['linear'],\
                gaintable=gaintables+['cal/'+s.name+'/gain'+str(cycle)+'-boot.Gp'])
            FlagCal('cal/'+s.name+'/gain'+str(cycle)+'.K', sigma = 5, cycles = 3)
            plotGainCal('cal/'+s.name+'/gain'+str(cycle)+'.K', delay=True)

            default('gaincal')
            gaincal(vis=active_ms, caltable='cal/'+s.name+'/gain'+str(cycle)+'.Gp', field=s.g+','+s.f, selectdata=True,\
            	uvrange='>100m', scan=",".join(filter(None, [s.fscan,s.gscan])), solint='int', refant=refAnt, \
                minblperant=minBL_for_cal, minsnr=minsnr, calmode='p', gaintable=gaintables+['cal/'+s.name+'/gain'+str(cycle)+'.K'], interp=interp+['linear'])

            default('smoothcal')
            smoothcal(vis=active_ms, tablein='cal/'+s.name+'/gain'+str(cycle)+'.Gp',\
            	caltable='cal/'+s.name+'/gain'+str(cycle)+'.Gp-smooth')

            plotGainCal('cal/'+s.name+'/gain'+str(cycle)+'.Gp-smooth', phase=True)

            gaintables.append('cal/'+s.name+'/gain'+str(cycle)+'.Gp-smooth')
            interp.append('linear')
    
            # Gain cal amp
            if freq < 500e6:
                minsnr=3.0
            else:
                minsnr=5.0
            default('gaincal')
            gaincal(vis=active_ms, caltable='cal/'+s.name+'/gain'+str(cycle)+'.Ga', field=s.g+','+s.f,\
            	selectdata=True, uvrange='>100m', scan=",".join(filter(None, [s.fscan,s.gscan])), \
                solint='60s', minsnr=minsnr, refant=refAnt, minblperant=minBL_for_cal, calmode='a', gaintable=gaintables)
            FlagCal('cal/'+s.name+'/gain'+str(cycle)+'.Ga', sigma = 3, cycles = 3)
    
            # if gain and flux cal are the same the fluxscale cannot work
            # do it only in the last cycle, so the next clip can work, otherwise the uvsub subtract
            # a wrong model for (amp==1) for the gain_cal if it had been rescaled
            if s.g != s.f and cycle == n_cycles-1:
                # fluxscale
                logging.debug("Rescale gaincal sol with fluxcal sol.")
                default('fluxscale')
                fluxscale(vis=active_ms, caltable='cal/'+s.name+'/gain'+str(cycle)+'.Ga',\
                	fluxtable='cal/'+s.name+'/gain'+str(cycle)+'.Ga_fluxscale', reference=s.f, transfer=s.g)

                plotGainCal('cal/'+s.name+'/gain'+str(cycle)+'.Ga_fluxscale', amp=True)
                gaintables.append('cal/'+s.name+'/gain'+str(cycle)+'.Ga_fluxscale')
                interp.append('linear')
            else:
                plotGainCal('cal/'+s.name+'/gain'+str(cycle)+'.Ga', amp=True)
                gaintables.append('cal/'+s.name+'/gain'+str(cycle)+'.Ga')
                interp.append('linear')
     
            # BLcal TODO: do BLcal on the fluxcal?
            #if s.f in s.fmodel:
            #    print "WARNING: flux_cal has a model and its being used for BLCAL, model must be superprecise!" 
            #blcal(vis=active_ms, caltable='cal/'+s.name+'/gain'+str(cycle)+'.BLap',  field=s.f,\
            #    scan=s.fscan, combine='', solint='inf', calmode='ap', gaintable=gaintables, solnorm=True)
            #FlagBLcal('cal/'+s.name+'/gain'+str(cycle)+'.BLap', sigma = 3)
            #plotGainCal('cal/'+s.name+'/gain'+str(cycle)+'.BLap', amp=True, phase=True, BL=True)
            #gaintables.append('cal/'+s.name+'/gain'+str(cycle)+'.BLap')
            #interp.append('nearest')

            default('applycal')
            applycal(vis=active_ms, field=s.g, scan=s.gscan, gaintable=gaintables, interp=interp,\
                calwt=False, flagbackup=False)
            
            # clip of residuals not on the last cycle (useless and prevent imaging of calibrator)
            if cycle != n_cycles-1:
                clipresidual(active_ms, f=s.g, s=s.gscan)

            # store list of gaintables to apply later
            s.gaintables = gaintables
            s.interp = interp

        # make a test img of the gain cal to check that everything is fine
        parms = {'vis':active_ms, 'field':s.g, 'imagename':'img/'+s.name+'_gcal', 'gridmode':'widefield', 'wprojplanes':128,\
              	'mode':'mfs', 'nterms':2, 'niter':1000, 'gain':0.1, 'psfmode':'clark', 'imagermode':'csclean',\
           	    'imsize':512, 'cell':sou_res, 'weighting':'briggs', 'robust':0, 'usescratch':False}
        cleanmaskclean(parms, s, makemask=False)
    
    # use a different cycle to compensate for messing up with uvsub during the calibration of other sources
    # in this way the CRRECTED_DATA are OK for all fields
    for s in sources:

        # apply B, Gp, Ga
        default('applycal')
        applycal(vis=active_ms, field=s.f,\
        	scan=s.fscan, gaintable=s.gaintables, \
            gainfield=[s.f, s.f, s.f],\
        	interp=s.interp, calwt=False, flagbackup=False)
        default('applycal')
        applycal(vis=active_ms, field=s.g,\
        	scan=",".join(filter(None, [s.fscan,s.gscan])), gaintable=s.gaintables, \
            gainfield=[s.f, s.g, s.g],\
        	interp=s.interp, calwt=False, flagbackup=False)
        default('applycal')
        applycal(vis=active_ms, field=s.t,\
        	scan=",".join(filter(None, [s.fscan,s.gscan,s.tscan])), gaintable=s.gaintables, \
            gainfield=[s.f, s.g, s.g], \
        	interp=s.interp, calwt=False, flagbackup=False)

    
#######################################
# SelfCal

def step_selfcal(active_ms, freq, minBL_for_cal):    
    logging.info("### SELFCAL")

    if freq > 1000e6: width = 16
    if freq > 550e6 and freq < 650e6: width = 16
    if freq > 300e6 and freq < 350e6: width = 8
    if freq > 200e6 and freq < 300e6: width = 8
    # renormalize if chans were not 512, force int to prevent bug in split() if width is a numpy.int64
    width = int(width / (512/sum(n_chan)))
    logging.info("Average with width="+str(width))
   
    for s in sources:

        check_rm('plots/'+s.name+'/self')
        os.makedirs('plots/'+s.name+'/self')
        check_rm('img/'+s.name)
        os.makedirs('img/'+s.name)
        check_rm('cal/'+s.name+'/self')
        os.makedirs('cal/'+s.name+'/self')
        check_rm('target_'+s.name+'.ms')
    
        default('split')
        split(vis=active_ms, outputvis=s.ms,\
        	field=s.t, width=width, datacolumn='corrected', keepflags=False)
    
        for cycle in xrange(6):
     
            logging.info("Start SELFCAL cycle: "+str(cycle))
            
            # save flag for recovering
            default('flagmanager')
            flagmanager(vis=s.ms, mode='save', versionname='selfcal-c'+str(cycle))

            ts = str(s.expnoise*10*(5-cycle))+' Jy' # expected noise this cycle
            parms = {'vis':s.ms, 'imagename':'img/'+s.name+'/self'+str(cycle), 'gridmode':'widefield', 'wprojplanes':512,\
          	    'mode':'mfs', 'nterms':2, 'niter':10000, 'gain':0.1, 'psfmode':'clark', 'imagermode':'csclean',\
           	    'imsize':sou_size, 'cell':sou_res, 'weighting':'briggs', 'robust':rob, 'usescratch':True, 'mask':s.mask,\
                'threshold':ts, 'multiscale':s.multiscale}
            cleanmaskclean(parms, s)

            # Get img rms and if it higher apply old gaintables/flags and quit
            rms = imstat(imagename='img/'+s.name+'/self'+str(cycle)+'-masked.image.tt0',mask='img/'+s.name+'/self'+str(cycle)+'\-masked.mask < 1')['rms'][0] # "<1" is to invert the mask
            if cycle != 0 and old_rms * 1.1 < rms:
                logging.warning('Image rms noise ('+str(rms)+' Jy/b) is higher than previous cycle ('+str(old_rms)+' Jy/b). Apply old cal tables and quitting selfcal.')

                # rename last image so peeling doesn't use it
                os.system('cd img/'+s.name+' && rename s/self'+str(cycle)+'/badimage/ *')

                # get previous flags
                default('flagmanager')
                flagmanager(vis=s.ms, mode='restore', versionname='selfcal-c'+str(cycle-1))
                
                # for the first cycle just remove all calibration i.e. no selfcal
                # for the others get the previous (i.e. cycle-2) cycle tables
                if cycle == 1:
                    default('clearcal')
                    clearcal(vis=s.ms)
                elif cycle < 4:
                    plotGainCal('cal/'+s.name+'/self/gain'+str(cycle-2)+'.Gp', phase=True)
                    default('applycal')
                    applycal(vis=s.ms, gaintable=gaintable, interp=['linear','linear'], calwt=False, flagbackup=False)           
                elif cycle >= 4: 
                    plotGainCal('cal/'+s.name+'/self/gain'+str(cycle-2)+'.Gp', phase=True)
                    plotGainCal('cal/'+s.name+'/self/gain'+str(cycle-2)+'.Ga', amp=True)
                    default('applycal')
                    applycal(vis=s.ms, gaintable=gaintable, interp=['linear','linear'], calwt=False, flagbackup=False)           

                break

            elif cycle != 0:
                logging.info('Rms noise change: '+str(old_rms)+' Jy/b -> '+str(rms)+' Jy/b.')

            if cycle == 5: break # don't do one more useless calibration

            old_rms = rms
 
            # ft() model back - if clean doesn't converge clean() fail to put the model, better do it by hand
            default('ftw')
            ftw(vis=s.ms, model=['img/'+s.name+'/self'+str(cycle)+'-masked.model.tt0','img/'+s.name+'/self'+str(cycle)+'-masked.model.tt1'], \
                    nterms=2, wprojplanes=512, usescratch=True)
            
            # recalibrating    
            refAntObj = RefAntHeuristics(vis=s.ms, field='0', geometry=True, flagging=True)
            refAnt = refAntObj.calculate()[0]

            # Gaincal - phases
            if cycle==0: 
                solint='600s'
                minsnr=4
            if cycle==1: 
                solint='120s'
                minsnr=3
            if cycle==2: 
                solint='30s'
                minsnr=3
            if cycle==3:
                solint='int'
                minsnr=2
            if cycle==4:
                solint='int'
                minsnr=2

            if freq < 400e6:
                minsnr -= 1.

            default('gaincal')
            gaincal(vis=s.ms, caltable='cal/'+s.name+'/self/gain'+str(cycle)+'.Gp', solint=solint, minsnr=minsnr,\
            	selectdata=True, uvrange='>50m', refant=refAnt, minblperant=minBL_for_cal, gaintable=[], calmode='p')

            # Delay correction: find leftover time-dependent delays
            # TODO: Is it a good way since delays are DDE?
#            if cycle >= 3:
#                default('gaincal')
#                gaincal(vis=s.ms, caltable='cal/'+s.name+'/self/gain'+str(cycle)+'.K', solint=solint, minsnr=minsnr,\
#                    selectdata=True, uvrange='>50m', refant=refAnt, minblperant=minBL_for_cal, gaintype='K', \
#                    interp=['linear'], gaintable=['cal/'+s.name+'/self/gain'+str(cycle)+'.Gp'])
#                # flag outliers
#                FlagCal('cal/'+s.name+'/self/gain'+str(cycle)+'.K', sigma = 5, cycles = 3)
#                plotGainCal('cal/'+s.name+'/self/gain'+str(cycle)+'.K', delay=True)
#                # apply just for propagate K flags
#                default('applycal')
#                applycal(vis=s.ms, field = '', gaintable=['cal/'+s.name+'/self/gain'+str(cycle)+'.K'], calwt=False, flagbackup=False, applymode='flagonly') 
            
            # Gaincal - amp
            if cycle >= 3:        
                    if cycle==3: 
                        solint='600s'
                        minsnr = 4.
                    if cycle==4: 
                        solint='300s'
                        minsnr = 3.
                    if freq < 400e6:
                        minsnr -= 1.
                    default('gaincal')
                    gaincal(vis=s.ms, caltable='cal/'+s.name+'/self/gain'+str(cycle)+'.Ga',\
                    	selectdata=True, uvrange='>50m', solint=solint, minsnr=minsnr, refant=refAnt,\
                    	minblperant=minBL_for_cal, gaintable=[], calmode='a')
                    FlagCal('cal/'+s.name+'/self/gain'+str(cycle)+'.Ga', sigma = 3, cycles = 3)
     
            # plot gains
            if cycle >= 3: 
                plotGainCal('cal/'+s.name+'/self/gain'+str(cycle)+'.Gp', phase=True)
                plotGainCal('cal/'+s.name+'/self/gain'+str(cycle)+'.Ga', amp=True)
            else:
                plotGainCal('cal/'+s.name+'/self/gain'+str(cycle)+'.Gp', phase=True)
            
            # add to gaintable
            if cycle >= 3: 
                gaintable=['cal/'+s.name+'/self/gain'+str(cycle)+'.Gp',\
                	'cal/'+s.name+'/self/gain'+str(cycle)+'.Ga']
                    #'cal/'+s.name+'/self/gain'+str(cycle)+'.K'
            else:
                gaintable=['cal/'+s.name+'/self/gain'+str(cycle)+'.Gp']

            default('applycal')
            applycal(vis=s.ms, field = '', gaintable=gaintable, interp=['linear','linear'], calwt=False, flagbackup=False)           
            statsFlag(s.ms, note='After apply selfcal (cycle: '+str(cycle)+')') 

        # end of selfcal loop
    
    # end of cycle on sources
  
    
#######################################
# Peeling
    
def step_peeling(): 
    logging.info("### PEELING")

    for s in sources:
        check_rm('img/'+s.name+'/peel*')
        check_rm('peel')
        os.makedirs('peel')
        modelforpeel = [sorted(glob.glob('img/'+s.name+'/self*-masked.model.tt0'))[-1], sorted(glob.glob('img/'+s.name+'/self*-masked.model.tt1'))[-1]]
        refAntObj = RefAntHeuristics(vis=s.ms, field='0', geometry=True, flagging=True)
        refAnt = refAntObj.calculate()[0]

        for i, sourcetopeel in enumerate(s.peel):

            s.ms = peel(s, modelforpeel, sourcetopeel, refAnt, rob, cleanenv=False)
 
            parms = {'vis':s.ms, 'imagename':'img/'+s.name+'/peel'+str(i), 'gridmode':'widefield', 'wprojplanes':512,\
            	'mode':'mfs', 'nterms':2, 'niter':10000, 'gain':0.1, 'psfmode':'clark', 'imagermode':'csclean',\
        	    'imsize':sou_size, 'cell':sou_res, 'weighting':'briggs', 'robust':rob, 'usescratch':True, 'mask':s.mask,\
                'threshold':str(s.expnoise)+' Jy', 'multiscale':s.multiscale}
            cleanmaskclean(parms, s)
       
            modelforpeel = ['img/'+s.name+'/peel'+str(i)+'-masked.model.tt0','img/'+s.name+'/peel'+str(i)+'-masked.model.tt1']

#######################################
# Subtract point sources
    
def step_subtract():
    logging.info("### SUBTRACTING")

    for s in sources:
        check_rm(s.ms+'-sub')
        check_rm('img/'+s.name+'/hires*')

        os.system('cp -r '+s.ms+' '+s.ms+'-sub')
        s.ms = s.ms+'-sub'

        # make a high res image to remove all the extended components
        parms = {'vis':s.ms, 'imagename':'img/'+s.name+'/hires', 'gridmode':'widefield', 'wprojplanes':512,\
           	'mode':'mfs', 'nterms':2, 'niter':5000, 'gain':0.1, 'psfmode':'clark', 'imagermode':'csclean',\
            'imsize':sou_size, 'cell':sou_res, 'weighting':'briggs', 'robust':rob-1, 'usescratch':True, 'mask':s.mask, \
            'selectdata':True, 'uvrange':'>4klambda','threshold':str(s.expnoise)+' Jy', 'multiscale':[]}
        cleanmaskclean(parms, s)

        # subtract 
        subtract(s.ms, ['img/'+s.name+'/hires-masked.model.tt0','img/'+s.name+'/hires-masked.model.tt1'], region=s.sub, wprojplanes=512)


#######################################
# Low-res clean
def step_lowresclean():
    logging.info("### LOW RESOLUTION CLEANING")

    for s in sources:
        check_rm('img/'+s.name+'/lowres*')

        parms = {'vis':s.ms, 'imagename':'img/'+s.name+'/lowres', 'gridmode':'widefield', 'wprojplanes':512,\
           	'mode':'mfs', 'nterms':2, 'niter':10000, 'gain':0.1, 'psfmode':'clark', 'imagermode':'csclean',\
            'imsize':sou_size, 'cell':sou_res, 'weighting':'briggs', 'robust':rob, 'usescratch':True, 'mask':s.mask, \
            'uvtaper':True, 'outertaper':[taper], 'threshold':str(s.expnoise)+' Jy', 'multiscale':s.multiscale}
        cleanmaskclean(parms, s)
        
        # pbcorr
        correctPB('img/'+s.name+'/lowres-masked.image.tt0', freq, phaseCentre=None)
 

# steps to execute
#step_env()
#step_import()
freq, minBL_for_cal, sources, n_chan = step_setvars(active_ms) # NOTE: do not commment this out!
#step_preflag(active_ms, freq, n_chan)
#step_setjy(active_ms)
#step_bandpass(active_ms, freq, n_chan, minBL_for_cal)
#step_calib(active_ms, freq, minBL_for_cal)
step_selfcal(active_ms, freq, minBL_for_cal)
step_peeling()
#step_subtract()
step_lowresclean()
