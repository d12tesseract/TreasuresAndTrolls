Create a python script to create a map in an SVG format from a 16 color bitmap.

White pixels count as empty space, black pixels count as solid walls, and red pixels are void

Create an SVG for an outline of all the white pixels, but skip the outline segments anywhere a red pixel touches a white pixel.

Default to a map scale of 10 feet per pixel, and the SVG scale will be 1 inch = 50 feet, or 5 pixels per inch.  The SVG line width will default to .01 inches, but another optional parameter can set another line width weight.

Also render each 1 pixel (or default 10 feet) line segment as a separate SVG line element, so that if the SVG is converted into an editable picture object line segments can be delet3ed or moved manually.  So, if a single white pixel is surroended by 8 black pixles, render 4 SVG line segments for all 4 edges of the white pixel, top, bottom, left, and right

## Usage

Requires Python 3.7+ and Pillow. Run from the repository root:

```powershell
python -m pip install Pillow
python campaigns\ur\pixelmap_bmp_to_svg.py campaigns\ur\map_1_1_gelatinous_cube_maze.bmp
```

The output defaults to the input filename with an `.svg` extension. To override
the output, map scale, print scale, or line width:

```powershell
python campaigns\ur\pixelmap_bmp_to_svg.py input.bmp --output output.svg --feet-per-pixel 10 --feet-per-inch 50 --line-width 0.01
```

The default line width is **0.01 inches**. Each pixel edge is 0.2 inches at
the default scale (10 feet per pixel, 50 feet per inch). A half-stroke margin
around the image prevents clipping without changing that scale.

Colors are matched by their exact RGB values, including for 16-color indexed
BMP palettes: white (`#FFFFFF`) is empty and red (`#FF0000`) is void. Only white
pixels produce lines. Edges shared with white or red pixels are omitted;
edges facing black or any other color, or the outside of the bitmap, are
outlined. Diagonal contact does not suppress edges. Every remaining pixel
edge is an independent, black SVG `<line>` with its own stroke attributes;
adjacent collinear edges are never merged.

Run the regression tests from the repository root:

```powershell
python -m unittest discover -s campaigns\ur -p test_pixelmap_bmp_to_svg.py
```