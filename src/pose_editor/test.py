import bpy

# Define the objects
obj_middle = bpy.data.objects["P3D.Harri_Hip"]
obj_a = bpy.data.objects["P3D.Harri_RHip"]
obj_b = bpy.data.objects["P3D.Harri_LHip"]

# Add drivers to X, Y, Z location of obj_middle
for i, axis in enumerate(["LOC_X", "LOC_Y", "LOC_Z"]):
    fcurve = obj_middle.driver_add("location", i)
    driver = fcurve.driver
    driver.type = 'SCRIPTED'

    # Variable for obj_a
    var_a = driver.variables.new()
    var_a.name = "a"
    var_a.type = 'TRANSFORMS'
    var_a.targets[0].id = obj_a
    var_a.targets[0].transform_type = axis
    var_a.targets[0].transform_space = 'WORLD_SPACE'

    # Variable for obj_b
    var_b = driver.variables.new()
    var_b.name = "b"
    var_b.type = 'TRANSFORMS'
    var_b.targets[0].id = obj_b
    var_b.targets[0].transform_type = axis
    var_b.targets[0].transform_space = 'WORLD_SPACE'

    # Expression to compute midpoint
    driver.expression = "(a + b) / 2"
