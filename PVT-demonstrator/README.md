# Native P-v-T AZEL Demonstrator

From the repository root, run `run_pvt_demonstrator.bat` in Command Prompt.

This is the Tkinter/Matplotlib AZEL edition of the native P-v-T teaching
application. Its 3D mouse interaction is fixed to elevation/azimuth rotation,
so dragging cannot introduce camera roll. Reset, front, side, top, and
isometric camera buttons are included.

The demonstrator includes:

- five working fluids;
- a corrected continuous liquid/two-phase surface;
- a smooth saturation boundary;
- a solid dark-blue isotherm;
- translucent pressure and temperature slicing planes;
- balanced 3D box proportions;
- camera preservation during slider updates;
- the UTM logo and attribution footer.

The previously delivered native source is preserved unchanged as
`pvt_native_backup.py`.

On first use, run `setup_windows.bat` from the repository root. The included
`Install and run.docx` provides additional Windows setup instructions.
