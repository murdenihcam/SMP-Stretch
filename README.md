# - *ੈ✩‧₊˚murdenihcam USR machines˖⁺‧₊˚✧ - 
This is a repository containing all of the USR machines that I have released for the [MDX X20 firmware](https://github.com/jmamma/MDX). 
- Discussion thread here: [Custom USR Machines for X.20](https://www.elektronauts.com/t/custom-usr-machines-for-x-20/257233). 
- Here's an MD/MnM community discord that I use to discuss this: https://discord.gg/HNtQsSmkf
---

**important disclaimers**:
I have tested these new machines a bunch already and tweaked them but it should of course go without saying, as Justin mentions in the release of X.20B, that you install third-party machines at your own risk. Back up your machine before doing any of this, including upgrading the firmware. That said, all of this appears to be running very smoothly on the UW+ MKII. Finally, I’m not affiliated with the development of MDX in any way, just a member of the community who is very excited about the possibilities of this firmware! 

**how to install (applies to any USR machine)**:
_requirements:_ As I understand it, you can use **any** MD updated to [X.20B firmware available here](https://github.com/jmamma/MDX) to install machines from the folder of machines provided by MDX that comes in the firmware ZIP. This is also true of my E12-only sample playback machines, which work on your internal E12 samples, as well as NFX modules.
To install my *ROM and E12* machines (SMP-ST) or the ROM-only versions, you’ll need a Machinedrum UW (MKI or II, + or not) on X.20B.

1. Locate a USR machine .syx that you want to install (eg one of the many that come with X.20 and/or my machine(s)--.syx to be found in respective folders here) and drag these into Sysex Librarian (or your sysex app of choice)
2. connect the MD to your midi interface 
3. FUNC+GLOBAL, FILE --> MACHINE MGR. Choose an empty slot, select RECV. It will say WAITING...
4. Using Sysex Librarian, play the .syx file(s) to the MD. You can select multiple .syx and play all at once; the machine bank will populate empty slots automatically. this is usually a very quick transfer as these are small files. The machine will then install. 
5. When you go to KIT-->EDIT, you may now see new machine categor(ies) corresponding to the new machine and you're good to go. Notably several of the ones from MDX will be found in existing categories like NFX and P-I. We’re limited to 16 slots but with a + drive you can have multiple Machine Banks. (moreover I’m told that the exciting https://kitbasher.xyz project will soon be updated to support X.20, where you’ll then be able to add further machines at the level of firmware, but I digress)

# **machine descriptions:**


## **SMP-ST[RETCH]** 
<img width="1473" height="230" alt="SMP-ST" src="https://github.com/user-attachments/assets/045f9338-a97d-4bf4-b034-74f0a374cc60" />

<img width="192" height="144" alt="SMP-ST_logo_web" src="https://github.com/user-attachments/assets/184df9b1-042f-4742-97e0-c798d60947c7" />
<img width="192" height="144" alt="SMP-SR_logo_web" src="https://github.com/user-attachments/assets/b9ac8ede-a092-4e65-a0aa-90c8f4ea5752" />
<img width="192" height="144" alt="SMP-S2_logo_web" src="https://github.com/user-attachments/assets/c465f351-2075-4fc2-b304-5af78af83603" />

**what it is**
A custom sample timestretching machine for the Elektron Machinedrum, compatible with the [X.20 firmware](https://github.com/jmamma/MDX). I wanted to make an homage to the Ableton texture warp mode: that gritty, Akai S950 kind of timestretch sound. This machine is focused on the textural exploration of slowing down the sample and altering the grain size and flux (jitter of grains). There are **3 versions depending on compatibility and/or your preferred use case (see dl links below):** one that addreses samples in UW ROM and E12, one for just the UW ROM, and one that just looks at *internal* E12 samples (the latter being compatible with all models). 

**parameters**
Here you get a SMPL knob for selecting the respective sample slot to address (plockable of course) -- another side benefit of this is you don't have to dig thru ROM/E12 to find your sample, a DECay, the TIME knob, which starts at no stretch and increases to infinite freeeeeeeeeeze. GRAN and FLUX are designed to work like ableton's texture warp, and unlike in Ableton, we can actually modulate these params!!! have fun sssttrrreeeetttttccccchhhhiiiiiiiiiiiinnnnnggggggggg :slight_smile: 

<img width="375" height="500" alt="cd4e9815e1427f9ffd8483e6518562df343691ba_2_750x1000" src="https://github.com/user-attachments/assets/66674c9e-df71-4509-8130-aabe4dc5b014" />



**NOTE:** One current bug to be aware of with all USR machines that I encountered is that if you have a kit loaded that uses USR machines and you install new machines, those that were in your current pattern might start sounding glitchy. This is temporary and is quickly resolved by reloading the kit or power cycling.

–––––––––––––––––––––
