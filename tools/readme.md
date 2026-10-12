# Tools

Tools and utilites

- [BMP line drawing to SVG](bmp_to_svg.md): Algorithm and usage for [bmp_to_svg.py](bmp_to_svg.py), which converts an ink line drawing bitmap into an SVG line drawing.  Just draw your map, scan it as a BMP, and convert it to an SVG.
- [Merge SVG files](merge_svg.md): Usage and YAML layout options for [merge_svg.py](merge_svg.py), which combines SVG files with scaling, reflection, rotation, and positioning.  Used mainly to combine orthogonal pixel map based dungeon maps from pixelmap_bmp_to_svg with hand drawn SVG vector maps for natural caverns from bmp_to_svg into a single combined dungeon map.
- [ASCII and procedural dungeon maps](generate_dungeon_map.md): Generates a complete random multi level dungeon map with encounters, or will create a custom dungeon map from an ASCII text file.  Can be used to create a full dungeon map of 10 or more levels with hundreds of pre-generated encounters, traps, and secrets
- [generate_graph_paper.py](generate_graph_paper.py): Generates blank square or hexagonal SVG graph paper with configurable dimensions, density, and hexagon orientation.
- [generate_map_projection.py](generate_map_projection.py): Generates a 12 sided map projection outline for global maps as an SVG and JSON describing the 3D solid and unfolded 2D geometry. 
- [pixelmap_bmp_to_svg.py](pixelmap_bmp_to_svg.py): Tool for generating a simple dungeond map from a black and white pixel map.  Outlines white bitmap regions as wall lines in SVG, omitting shared white/white and white/red edges and applying configurable physical scaling. 
