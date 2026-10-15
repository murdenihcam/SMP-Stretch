@echo off
rem Build one machine on Windows: assemble -> pack (.mds) -> SysEx (.syx).
rem Usage:   build.cmd ram_probe 2
rem Needs NAME.asm56k and NAME.json in the current folder, and Python 3 on the PATH.
rem Set these once per command window (adjust the paths):
rem   set DSP56300_TOOLS=C:\dsp56300tools
rem   set MDS_REPO=C:\MDS
rem Optional, when the JSON has no max_track_cycles:  set MAX_CYCLES=2169
setlocal
if "%DSP56300_TOOLS%"=="" (echo Set DSP56300_TOOLS to the folder holding asm56300.exe and cldlod.exe & exit /b 1)
if "%MDS_REPO%"=="" (echo Set MDS_REPO to the folder where the MDS repo was unpacked & exit /b 1)
set NAME=%1
if "%NAME%"=="" (echo Usage: build.cmd NAME [slot 1..16] & exit /b 1)
set SLOT=%2
if "%SLOT%"=="" set SLOT=1
rem Absolute-mode assembly: -a absolute, -b writes NAME.cld (without it no object file is made), -l writes NAME.lst
if "%ASM_FLAGS%"=="" set ASM_FLAGS=-a -b -l
set CYC=
if not "%MAX_CYCLES%"=="" set CYC=--max-track-cycles %MAX_CYCLES%
rem Optional machine sprite for the MACHINE MGR: NAME.pbm, a 32x24 ASCII PBM (P1).
set BMP=
if exist %NAME%.pbm set BMP=--bitmap %NAME%.pbm

if not exist %NAME%.asm56k (echo Cannot find %NAME%.asm56k in %CD% - run this from the machine folder & exit /b 1)
del /q %NAME%.cld %NAME%.mds %NAME%.syx 2>nul
rem The old assembler only accepts .asm sources: assemble a copy named NAME.asm (edit NAME.asm56k, not the copy).
copy /y %NAME%.asm56k %NAME%.asm >nul
"%DSP56300_TOOLS%\asm56300.exe" %ASM_FLAGS% %NAME%.asm
if not exist %NAME%.cld (echo Assembling did not produce %NAME%.cld - see the messages above & exit /b 1)
python "%MDS_REPO%\tools\mds_pack.py" %NAME%.json %NAME%.cld --dsp-tools "%DSP56300_TOOLS%" %CYC% %BMP% -o %NAME%.mds || exit /b 1
python "%MDS_REPO%\tools\mds_to_syx.py" %NAME%.mds --slot %SLOT% -o %NAME%.syx || exit /b 1
echo Done: %NAME%.syx
