#!/usr/bin/env python
"""
| File: 12_python_single_vehicle_gsl_benchmark.py
| Author: Hajo Erwich (h.h.erwich@student.tudelft.nl)
| License: BSD-3-Clause. Copyright (c) 2023, Hajo Erwich. All rights reserved.
| Description: This files serves as an example on how to run a GSL benchmark with the benchmark.py script
"""
import os
import ast
import sys # get exp id and init pos
import yaml
import glob
import numpy as np
from datetime import datetime
from pathlib import Path

argv = sys.argv
argv = argv[argv.index("--") + 1:] # get all the args after " -- "
exp_id = argv[0]    # experiment id
env_id = argv[1]    # environment id
exp_pos = argv[2]   # initial posisiton

# Imports to start Isaac Sim from this script
import carb
from omni.isaac.kit import SimulationApp

# Start Isaac Sim's simulation environment
# Note: this simulation app must be instantiated right after the SimulationApp import, otherwise the simulator will crash
# as this is the object that will load all the extensions and load the actual simulator.
simulation_app = SimulationApp({"headless": True})

# -----------------------------------
# The actual script should start here
# -----------------------------------
import omni.timeline
from omni.isaac.core.world import World

# Import the Pegasus API for simulating drones
from pegasus.simulator.params import ROBOTS, SIMULATION_ENVIRONMENTS
from pegasus.simulator.logic.vehicles.multirotor_gsl import Multirotor, MultirotorConfig
from pegasus.simulator.logic.interface.pegasus_interface import PegasusInterface

# Import the custom python control backend and end conditions
from examples.utils.nonlinear_controller_ecoli_oa import NonlinearController
#from examples.utils.nonlinear_controller_dungbeetle_oa import NonlinearController # change this line for a different algorithm
from pegasus.simulator.logic.gsl.stop_conditions import StopCondition

# Auxiliary scipy and numpy modules
from scipy.spatial.transform import Rotation

class PegasusApp:
    """
    A Template class that serves as an example on how to build a simple Isaac Sim standalone App.
    """

    def __init__(self, id:str, env_id:int, pos:list):
        """
        Method that initializes the PegasusApp and is used to setup the simulation environment.
        """
        self.start_time = datetime.now() # For timing the runs afterwards
        self.curr_dir = str(Path(os.path.dirname(os.path.realpath(__file__))).resolve()) # Get current directory

        # Select the environment directory
        self.env_dir = self.curr_dir + f"/environments/{str(env_id).zfill(3)}/"

        # Environment specifications
        with open(glob.glob(f"{self.env_dir}occupancy/*head.txt")[0], 'r') as file:
            env_spec = yaml.safe_load(file)

        # Combine environment info into env_dict
        env_dict = {"env_dir": self.env_dir,
                    #"env_type": env_type,
                    "env_id": env_id,
                    #"env_name": env_name,
                    "env_spec": env_spec}

        # Acquire the timeline thatfwill be used to start/stop the simulation
        self.timeline = omni.timeline.get_timeline_interface()

        # Start the Pegasus Interface
        self.pg = PegasusInterface()

        # Acquire the World, .i.e, the singleton that controls that is a one stop shop for setting up physics, 
        # spawning asset primitives, etc.
        self.pg._world = World(**self.pg._world_settings)
        self.world = self.pg.world

        # Launch one of the worlds provided AutoGDM2
        #self.pg.load_environment(f'{AutoGDM2_dir}environments/isaac_sim/{env_name}.usd')
        self.pg.load_environment(glob.glob(f"{self.env_dir}usd/*.usd")[0])
        
        # Set spawn position of the multirotor and experiment ID
        self.exp_id = id
        init_pos_1 = pos
        
        # Auxiliar variable for repeated runs
        self.save_statistics = True
        self.runs = 10
        self.statistics = [f"{self.exp_id}_ecoli_{i}" for i in range(self.runs)]

        # Set sensor parameters
        mox_config = {"env_dict": env_dict,
                      "draw": False,                 # draw the filaments
                      "sensor_model": 1,            # ["TGS2620", "TGS2600", "TGS2611", "TGS2610", "TGS2612"]
                      "gas_type": 0,                # 0=Ethanol, 1=Methane, 2=Hydrogen # TODO - get from settings!
                      "update_rate": 4.0,           # [Hz] update rate of sensor
                      "gas_data_time_step": 0.5,    # [s] time steps between gas data iterations (in seconds to match GADEN)
                      "gas_data_start_iter": 300,   # start iteration
                      "gas_data_stop_iter": 0}      # stop iteration (0 -> to the last iteration)
        
        pid_config = {"env_dict": env_dict,      # dict with environment info
                      "draw": False,              # draw the filaments
                      "gas_type": 0,             # 0=Ethanol, 1=Methane, 2=Hydrogen
                      "use_correction": True,    # use correction factor
                      "update_rate": 4.0,        # [Hz] update rate of sensor
                      "gas_data_time_step": 0.5, # [s] time steps between gas data iterations (in seconds to match GADEN)
                      "gas_data_start_iter": 300,# start iteration
                      "gas_data_stop_iter": 0}   # stop iteration (0 -> to the last iteration)

        anemo_config = {"env_dict": env_dict,
                        "update_rate": 10.0,  # [Hz] update rate of sensor
                        "wind_data_time_step": 1.0, # [s] time steps between wind data iterations
                        "wind_data_start_iter": 0,  # start iteration
                        "wind_data_stop_iter": 0}   # stop iteration (0 -> to the last iteration)
        
        sensor_configs = {'gas_sensor_type': 'mox', # select gas sensor type here: 'mox', 'pid'
                          'mox': mox_config,
                          'pid': pid_config,
                          'anemometer': anemo_config}
        # Create the vehicle 1
        # Try to spawn the selected robot in the world to the specified namespace
        config_multirotor1 = MultirotorConfig(sensor_configs=sensor_configs)
        self.controller = NonlinearController(
            init_pos=init_pos_1,
            env_dict=env_dict,
            Ki=[0.5, 0.5, 0.5],
            Kr=[2.0, 2.0, 2.0]
        )
        config_multirotor1.backends = [self.controller]

        Multirotor(
            "/World/quadrotor1",
            ROBOTS['Iris'],
            0,
            init_pos_1,
            Rotation.from_euler("XYZ", [0.0, 0.0, 0.0], degrees=True).as_quat(),
            config=config_multirotor1,
        )

        if (int(env_id)%2) == 0:
            self.source_pos = np.array([1.0, 10.0, 2.0]) # TODO - read source_pos from settings
        else:
            self.source_pos = np.array([5.0, 1.0, 2.0])

        # Set stop condition(s)
        self.stop_cond = StopCondition(time=300.0,
                                       source_pos=self.source_pos, 
                                       distance2src=1.0)
        
        # Set the camera to a nice position so that we can see the environment
        self.pg.set_viewport_camera([0.5, 0.5, (env_spec["env_max"][2] + 5)], [i*0.5 for i in env_spec["env_max"]])
        
        # Reset the simulation environment so that all articulations (aka robots) are initialized
        self.world.reset()


    def run(self):
        """
        Method that implements the application main loop, where the physics steps are executed.
        """
        
        # Run the simulation again for every statistics file
        for i,statistics_file in enumerate(self.statistics):
            # Set the results file
            if self.save_statistics:
                self.controller.results_files = self.curr_dir + f"/results/{self.exp_id}/{statistics_file}.npz"
                #self.controller.results_files = f"/home/hajo/0THESIS/experiments/{self.exp_id}/{statistics_file}.npz"

            # Start the simulation
            self.timeline.play()

            while not self.stop_cond.get(time_current = self.controller.total_time,
                                         pos_current = self.controller.p):
                # Update the UI of the app and perform the physics step
                self.world.step(render=False)

            if self.stop_cond.type == "dist2src": # mark the run as a success if the source is considered found
                self.controller.run_success[0] = True

            # Stop & Reset the simulation
            self.timeline.stop()
            self.world.reset() # necessary to replicate the 'UI stop button' behaviour
            carb.log_warn(f"Finished run {i+1}/{self.runs}")
        
        # Cleanup and quit
        carb.log_warn("PegasusApp Simulation App is closing.")
        carb.log_warn(f"Finished experiment {self.exp_id} in {datetime.now() - self.start_time}")
        simulation_app.close()


def main():
    # Instantiate the template app with experiment id and position
    pg_app = PegasusApp(id=exp_id, env_id=env_id, pos=ast.literal_eval(exp_pos))

    # Run the application loop
    pg_app.run()


if __name__ == "__main__":
    main()
