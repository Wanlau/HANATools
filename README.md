# HANATools
Tools for Sonohana???

It seem there are some bugs when converting the mode-1 MGD to png. (such as: GS_EN_SN.MGD in HANA01)

Unpack fjsys:
```
python HANATools_main.py -m ufj -i [intput_file] -od [output_directory]
```

Unpack fjsys with password(only for decrypting MSD):
```
python HANATools_main.py -m ufj -i [intput_file] -od [output_directory] -pw [password]
```

Convert MGD to png:
```
python HANATools_main.py -m umg -i [intput_file] -od [output_directory]
```

For help:
```
python HANATools_main.py -h
```