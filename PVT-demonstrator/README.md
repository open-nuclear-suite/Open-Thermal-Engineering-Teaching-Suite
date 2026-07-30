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
- FKM and HiREF branding, a three-second splash screen, and an attribution
  footer.

Thermophysical properties are calculated with
[CoolProp](https://coolprop.org/). Academic users should cite:

Bell, I. H., Wronski, J., Quoilin, S., & Lemort, V. (2014). Pure and
pseudo-pure fluid thermophysical property evaluation and the open-source
thermophysical property library CoolProp. *Industrial & Engineering Chemistry
Research, 53*(6), 2498–2508.
[https://doi.org/10.1021/ie4033999](https://doi.org/10.1021/ie4033999)

The previously delivered native source is preserved unchanged as
`pvt_native_backup.py`.

On first use, run `setup_windows.bat` from the repository root. The included
`Install and run.docx` provides additional Windows setup instructions.
