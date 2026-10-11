# SMP-SL[icer]

<img width="962" height="612" alt="smp-sl pic" src="https://github.com/user-attachments/assets/7a417b08-9266-42b8-9c5f-da46271cdbc4" />

<img width="192" height="144" alt="e12_slicer_web" src="https://github.com/user-attachments/assets/81f9dbfa-79f0-42a9-82f0-e5eb22589f6e" />
<img width="192" height="144" alt="rom_slicer_web" src="https://github.com/user-attachments/assets/598b312a-bcf4-46ec-abcf-fe7d2196271a" />
<img width="192" height="144" alt="rom_e12_slicer_web" src="https://github.com/user-attachments/assets/625f11fe-8167-4c7c-a487-f741ff9f4f93" />

**what it is**
A sample slicer and looper for the Machinedrum, compatible with the [X.20 firmware](https://github.com/jmamma/MDX) . Fun with longer samples but can also get interesting textural results with shorter ones. the magic comes with plocking the SLNO parameter (slice number!)

**parameters**

**PTCH** - half a semitone per step (±32 semitones). It changes speed as well. This interacts with TIME in interesting ways.

**SMPL** - Which sample: 1–48 are the UW ROM slots, E1–E21 the internal samples. Takes effect at the next trig.

**DEC -** 0: plays the slice once at full level. 1–126: decay from about 0.03 s to 30 s, with the slice looping in the PLAY direction while it’s audible. 127: no decay, loops forever.

**TIME** - 0: normal playback. Above 0, slows the slice down without changing pitch. 42: half speed. 127: frozen in place.

**MODE -** How the sample is sliced.. EQUA: equal slices. EXP: slices get longer along the sample. LOG: slices get shorter along the sample. SED1–SED4: 4 diifferent fixed random-width seeds. Takes effect at the next trig.

**PLAY** - Direction of playback. FWD: forwards. REV: backwards. BI: turns round at each end of the slice. When DEC loops, it’s checked at every loop, so you can change it while a slice is held.

**SLIC** - Number of slices across the whole sample. Takes effect at the next trig.

**SLNO** - Which slice plays. Values above SLIC wrap round (for example SLNO 10 with 8 slices plays slice 2). Takes effect at the next trig.

**how to install (applies to any USR machine)**:
requirements: As I understand it, you can use **any** MD updated to [X.20B firmware available here](https://github.com/jmamma/MDX) to install machines from the folder of machines provided by MDX that comes in the firmware ZIP. This is also true of my E12 version which works on your internal E12 samples.
To install my *ROM and E12* machine or the ROM-only version, you’ll need a Machinedrum UW (MKI or II, + or not) on X.20B.

1. Locate a USR machine .syx that you want to install (eg one of the many that come with X.20 and/or my machine(s) and drag these into Sysex Librarian (or your sysex app of choice)
2. connect the MD to your midi interface 
3. FUNC+GLOBAL, FILE --> MACHINE MGR. Choose an empty slot, select RECV. It will say WAITING...
4. Using Sysex Librarian, play the .syx file(s) to the MD. You can select multiple .syx and play all at once; the machine bank will populate empty slots automatically. this is usually a very quick transfer as these are small files. The machine will then install. 
5. When you go to KIT-->EDIT, you may now see new machine categor(ies) corresponding to the new machine and you're good to go. Notably several of the ones from MDX will be found in existing categories like NFX and P-I. We’re limited to 16 slots but with a + drive you can have multiple Machine Banks. (moreover I’m told that the exciting https://kitbasher.xyz project will soon be updated to support X.20, where you’ll then be able to add further machines at the level of firmware, but I digress)

**NOTE:** One current bug to be aware of with all USR machines that I encountered is that if you have a kit loaded that uses USR machines and you install new machines, those that were in your current pattern might start sounding glitchy. This is temporary and is quickly resolved by reloading the kit or power cycling.

Discussion thread about USR machines here: [Custom USR Machines for X.20](https://www.elektronauts.com/t/custom-usr-machines-for-x-20/257233)

–––––––––––––––––––––

**important disclaimers**
I have tested these new machines a bunch already and tweaked them but it should of course go without saying, as Justin mentions in the release of X.20B, that you install third-party machines at your own risk. Back up your machine before doing any of this, including upgrading the firmware. That said, all of this appears to be running very smoothly on the UW+ MKII (unknown on other hardware). Finally, I’m not affiliated with the development of MDX in any way, just a member of the community who is very excited about the possibilities of this firmware!
