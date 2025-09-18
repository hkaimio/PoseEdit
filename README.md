# Pose Data Editor

This is a Blender extension for editing raw motion capture data obtained from
vides and trignualting it to 3D markers. The project depends heavily on
[Pose2Sim] tool by David Pagnon & others - credits for most of the heavy duty
algorithm work go to him, I just packaged his work into an UI that serves my
purposes (and I hope it will be useful to others too!)

The extension is still under active development - feel free to try but there are
unimplemented features & rough edges (well, maybe cliffs) so you should be
familiar with Python to try it now. Stay tuned for a more polished release!

[This video](https://www.youtube.com/watch?v=UD7q4lEcN1E) gives overview on the
current features.

## Features

* Import 2D pose data, camera calibration & video from Pose2Sim

* Adjust synchronization of pose data & videos from multiple cameras

* Stitch consistent timeline for a person from multiple pieces if the object tracking algorithm has lost the person in middle of the clip

* Edit individual marker positions
'
* Triangulate 3D markers from the raw data, analyze the results & debug errors 

### Wish list for V1.0

* Filtering of raw & triangulated data

* Export data in OpenPOse & numpy formats

* Fitting Blender armature to the data (estimate person's dimensions & scale the
  armature accordingly)

* Animating the fitted armature based on the 3D markers and Blender IK solver


