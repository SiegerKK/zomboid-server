#!/usr/bin/env python3
"""Optional REAL FMOD 2.03.09 regression; OWNER-installed library only.

Creates an isolated NOSOUND_NRT system, a temporary synthetic tone and no
hardware output. No real game process, artist music, settings or world access.
Not run by generic CI because proprietary game libraries are not distributed.
"""
import ctypes as c, math,wave,struct,json
from pathlib import Path
import argparse,tempfile
cli=argparse.ArgumentParser(description=__doc__);cli.add_argument('--library',type=Path,required=True);args=cli.parse_args()
lib=args.library.resolve();f=c.CDLL(str(lib))
P=c.c_void_p;I=c.c_int;F=c.c_float;U=c.c_uint

def api(name,types):
 fn=getattr(f,'FMOD_'+name);fn.argtypes=types;fn.restype=I
 def call(*args):
  result=fn(*args)
  if result:raise RuntimeError(name+' result='+str(result))
 return call
create=api('System_Create',[c.POINTER(P),U]);out=api('System_SetOutput',[P,I]);fmt=api('System_SetSoftwareFormat',[P,I,I,I]);init=api('System_Init',[P,I,U,P]);createSound=api('System_CreateSound',[P,c.c_char_p,U,P,c.POINTER(P)]);play=api('System_PlaySound',[P,P,P,I,c.POINTER(P)]);update=api('System_Update',[P]);release=api('System_Release',[P]);dspcount=api('Channel_GetNumDSPs',[P,c.POINTER(I)]);getdsp=api('Channel_GetDSP',[P,I,c.POINTER(P)]);dsptype=api('DSP_GetType',[P,c.POINTER(I)]);numparams=api('DSP_GetNumParameters',[P,c.POINTER(I)]);getparam=api('DSP_GetParameterInfo',[P,I,c.POINTER(P)])
class Desc(c.Structure):_fields_=[('kind',I),('name',c.c_char*16),('label',c.c_char*16),('description',c.c_char_p)]
temporary=tempfile.TemporaryDirectory(prefix='radio-native-spatial-');p=Path(temporary.name)/'synthetic.wav'
with wave.open(str(p),'wb') as w:
 w.setnchannels(2);w.setsampwidth(2);w.setframerate(22050)
 w.writeframes(b''.join(struct.pack('<hh',int(5000*math.sin(n*2*math.pi*440/22050)),int(5000*math.sin(n*2*math.pi*660/22050))) for n in range(22050*5)))
import time
class Vec(c.Structure):_fields_=[('x',F),('y',F),('z',F)]
class Meter(c.Structure):_fields_=[('numsamples',I),('peak',F*32),('rms',F*32),('numchannels',c.c_short)]
listener=api('System_Set3DListenerAttributes',[P,I,c.POINTER(Vec),c.POINTER(Vec),c.POINTER(Vec),c.POINTER(Vec)]);attrs=api('Channel_Set3DAttributes',[P,c.POINTER(Vec),c.POINTER(Vec)]);range3d=api('Channel_Set3DMinMaxDistance',[P,F,F]);pause=api('Channel_SetPaused',[P,I]);group=api('System_GetMasterChannelGroup',[P,c.POINTER(P)]);gdsp=api('ChannelGroup_GetDSP',[P,I,c.POINTER(P)]);meterOn=api('DSP_SetMeteringEnabled',[P,I,I]);meter=api('DSP_GetMeteringInfo',[P,P,c.POINTER(Meter)]);stop=api('Channel_Stop',[P]);spread=api('Channel_Set3DSpread',[P,F])
rows=[]
for mode in [6]:
 sys=P();create(c.byref(sys),0x20309)
 try:
  out(sys,4);fmt(sys,32000,mode,0);init(sys,128,0x20300,None)
  sound=P();createSound(sys,str(p).encode(),0x80|0x10|2,None,c.byref(sound));channel=P();play(sys,sound,None,1,c.byref(channel))
  g=P();group(sys,c.byref(g));dsp=P();gdsp(g,-2,c.byref(dsp));meterOn(dsp,0,1)
  private=P();api('System_CreateChannelGroup',[P,c.c_char_p,c.POINTER(P)])(sys,b'SiegerRadioTestOnly',c.byref(private))
  fd=P();gdsp(private,-2,c.byref(fd))
  api('DSP_SetChannelFormat',[P,U,I,I])(fd,3,2,3)
  api('Channel_SetChannelGroup',[P,P])(channel,private)
  for angle in [0,90,180,270]:
   v=Vec();forward=Vec(math.cos(math.radians(angle)),math.sin(math.radians(angle)),0);up=Vec(0,0,1);source=Vec(1,0,0)
   listener(sys,0,c.byref(v),c.byref(v),c.byref(forward),c.byref(up));attrs(channel,c.byref(source),c.byref(v));range3d(channel,4,12);spread(channel,0);pause(channel,0)
   for i in range(30):update(sys);time.sleep(.003)
   info=Meter();meter(dsp,None,c.byref(info));levels=list(info.rms)[:info.numchannels]
   rows.append(dict(speaker_mode=mode,angle=angle,channels=info.numchannels,rms=levels));print(rows[-1],flush=True)
  assert len(rows)==4 and rows[2]['channels']==2
  assert min(rows[2]['rms'])>0.5*min(rows[0]['rms']), 'rear music lost'
  # Occupied-cabin width on same stream: front/side/rear must reach both ears.
  # Synthetic stereo has equal-power independent 440/660 Hz channels.
  for angle in [0,90,180,270]:
   origin=Vec();forward=Vec(math.cos(math.radians(angle)),math.sin(math.radians(angle)),0);up=Vec(0,0,1);source=Vec(1,0,0)
   listener(sys,0,c.byref(origin),c.byref(origin),c.byref(forward),c.byref(up));attrs(channel,c.byref(source),c.byref(origin));spread(channel,180)
   for i in range(30):update(sys);time.sleep(.003)
   info=Meter();meter(dsp,None,c.byref(info));levels=list(info.rms)[:info.numchannels]
   assert len(levels)==2 and min(levels)>.06 and max(levels)/min(levels)<1.05, 'cabin cardinal imbalance'
   print('Cabin180',angle,levels,flush=True)
  spread(channel,0) # exterior point source again, without restart or seek
  stop(channel)
  # A second unrelated world source stays in native surround on master.
  sentinel=P();play(sys,sound,None,1,c.byref(sentinel))
  origin=Vec();forward=Vec(1,0,0);up=Vec(0,0,1);behind=Vec(-1,0,0)
  listener(sys,0,c.byref(origin),c.byref(origin),c.byref(forward),c.byref(up));attrs(sentinel,c.byref(behind),c.byref(origin));range3d(sentinel,4,12);spread(sentinel,0);pause(sentinel,0)
  for i in range(30):update(sys);time.sleep(.003)
  info=Meter();meter(dsp,None,c.byref(info));print('Unrelated rear source',info.numchannels,list(info.rms)[:info.numchannels],flush=True)
  rate=I();smode=I();rawchannels=I();api('System_GetSoftwareFormat',[P,c.POINTER(I),c.POINTER(I),c.POINTER(I)])(sys,c.byref(rate),c.byref(smode),c.byref(rawchannels));assert smode.value==6
  assert info.numchannels==6 and info.rms[4]>0 and info.rms[0]==0
  print('PASS global 5.1 unchanged; unrelated source remains native surround',flush=True)
  stop(sentinel)
  api('ChannelGroup_Release',[P])(private)
 finally:release(sys)

print("PASS REAL FMOD: private stereo 3D rear audible, native 5.1 and unrelated sound unchanged")
temporary.cleanup()
