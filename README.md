# - *ੈ✩‧₊˚murdenihcam USR machines˖⁺‧₊˚✧ - 
This is a repository containing all of the USR machines that I have released for the [MDX X20 firmware](https://github.com/jmamma/MDX). 
- Discussion thread here: [Custom USR Machines for X.20](https://www.elektronauts.com/t/custom-usr-machines-for-x-20/257233). 
- Here's an MD/MnM community discord that I use to discuss this (see diy-machines) https://discord.gg/HNtQsSmkf
---

**important disclaimers**:
- I have tested these new machines a bunch already and tweaked them but it should of course go without saying, as Justin mentions in the release of X.20B, that you install third-party machines at your own risk. Back up your machine before doing any of this, including upgrading the firmware. That said, all of this appears to be running very smoothly on the UW+ MKII. 
- This is a project that is entirely conducted with LLM support for the coding. Development proceeded with lots of testing and iteration to tune the results.
- Finally, I’m not affiliated with the development of MDX in any way, just a member of the community who is very excited about the possibilities of this firmware! 

**how to install (applies to any USR machine)**:
- _requirements:_ As I understand it, you can use **any** MD updated to [X.20B firmware available here](https://github.com/jmamma/MDX) to install machines from the folder of machines provided by MDX that comes in the firmware ZIP. This is also true of my E12-only sample playback machines, which work on your internal E12 samples, as well as NFX modules.
To install my *ROM and E12* machines or the ROM-only versions, you’ll need a Machinedrum UW on X.20B.

1. Locate a USR machine .syx that you want to install (eg one of the many that come with X.20 and/or my machine(s)--.syx to be found in respective folders here) and drag these into Sysex Librarian (or your sysex app of choice)
2. connect the MD to your midi interface 
3. FUNC+GLOBAL, FILE --> MACHINE MGR. Choose an empty slot, select RECV. It will say WAITING...
4. Using Sysex Librarian, play the .syx file(s) to the MD. You can select multiple .syx and play all at once; the machine bank will populate empty slots automatically. this is usually a very quick transfer as these are small files. The machine will then install. 
5. When you go to KIT-->EDIT, you may now see new machine categor(ies) corresponding to the new machine and you're good to go. Notably several of the ones from MDX will be found in existing categories like NFX and P-I. We’re limited to 16 slots but with a + drive you can have multiple Machine Banks. 

**NOTE:** One current bug to be aware of with all USR machines that I encountered is that if you have a kit loaded that uses USR machines and you install new machines, those that were in your current pattern might start sounding glitchy. This is temporary and is quickly resolved by reloading the kit or power cycling.

# **machine descriptions:**

1. SMP-SL[ICE] (to be uploaded soon)
2. SMP-ST[RETCH]

## 1. SMP-SL[ICE]

<img width="481" height="306" alt="smp-sl pic" src="https://github.com/user-attachments/assets/d1255490-0b5a-4155-bebd-a3be1a904b9d" />\

<img width="96" height="72" alt="rom_e12_slicer_web" src="https://github.com/user-attachments/assets/108b719b-0604-4c72-b147-b4626d42c534" />
<img width="96" height="72" alt="rom_slicer_web" src="https://github.com/user-attachments/assets/6b9d3167-27cb-4f1e-a894-d57bac25a85c" />
<img width="96" height="72" alt="e12_slicer_web" src="https://github.com/user-attachments/assets/9a3e152f-50c7-4b00-a4ab-5e46c36da409" />

**what it is**
A transient-detecting sample slicer and looper for the Machinedrum, compatible with the [X.20 firmware](https://github.com/jmamma/MDX) . This is most fun with longer samples but you can also get interesting textural results with shorter ones. the magic comes with plocking the SLNO parameter (slice number!) Not sure how useful this is on just E12. I have a version somewhere that does things like equal and random slices, let me know if you want that.

**parameters**:\
**PTCH** - half a semitone per step (±32 semitones). It changes speed as well. This interacts with TIME in interesting ways.

**SMPL** - Which sample: 1–48 are the UW ROM slots, E1–E21 the internal samples. Takes effect at the next trig.

**DEC -** 0: plays the slice once at full level. 1–126: decay from about 0.03 s to 30 s, with the slice looping in the PLAY direction while it’s audible. 127: no decay, loops forever.

**TIME** - 0: normal playback. Above 0, slows the slice down without changing pitch, using a timestretching algorithm. 42: half speed. After 50% turn, grain sizes get smaller127: frozen in place (infinite repeat). DEC at 0 means no amp envelope on the time, decay at higher levels, there is.

**PLAY** - Direction of playback. FWD: forwards. REV: backwards. BI: turns round at each end of the slice. When DEC loops, it’s checked at every loop, so you can change it while a slice is held.

**THRS** - Threshold for transient slicing to occur. higher means fewer slices made.

**SLIC** - Number of slices across the whole sample. Takes effect at the next trig.

**SLNO** - Which slice plays. Values above SLIC wrap round (for example SLNO 10 with 8 slices plays slice 2). Takes effect at the next trig

---


## 2. SMP-ST[RETCH] (BETA)
<img width="1473" height="230" alt="SMP-ST" src="https://github.com/user-attachments/assets/045f9338-a97d-4bf4-b034-74f0a374cc60" />

<img width="96" height="72" alt="SMP-ST_logo_web" src="https://github.com/user-attachments/assets/c44f90f9-0f4b-4b98-adf2-392429df009f" />
<img width="96" height="72" alt="SMP-SR_logo_web" src="https://github.com/user-attachments/assets/e0e18002-96cc-42d9-9063-f250473682a6" />
<img width="96" height="72" alt="SMP-S2_logo_web" src="https://github.com/user-attachments/assets/900b2ee1-fe3c-4ba1-8877-fa4ea8fbd853" />

**NOTE:** Infinite decay/timestretch continues when changing to a new pattern. This can be stopped when the same track receives a new trig.

**what it is**
A custom sample timestretching machine for the Elektron Machinedrum, compatible with the [X.20 firmware](https://github.com/jmamma/MDX). I wanted to make an homage to the Ableton texture warp mode: that gritty, Akai S950 kind of timestretch sound. This machine is focused on the textural exploration of slowing down the sample and altering the grain size and flux (jitter of grains). There are **3 versions depending on compatibility and/or your preferred use case (see dl links below):** one that addreses samples in UW ROM and E12, one for just the UW ROM, and one that just looks at *internal* E12 samples (the latter being compatible with all models). 

**parameters**
Here you get a SMPL knob for selecting the respective sample slot to address (plockable of course) -- another side benefit of this is you don't have to dig thru ROM/E12 to find your sample, a DECay, the TIME knob, which starts at no stretch and increases to infinite freeeeeeeeeeze. GRAN and FLUX are designed to work like ableton's texture warp, and unlike in Ableton, we can actually modulate these params!!! have fun sssttrrreeeetttttccccchhhhiiiiiiiiiiiinnnnnggggggggg

<img width="187.5" height="250" alt="cd4e9815e1427f9ffd8483e6518562df343691ba_2_750x1000" src="https://github.com/user-attachments/assets/66674c9e-df71-4509-8130-aabe4dc5b014" />
---
