import timeit
import time
import sys
import os
from datetime import datetime
from typing import Union, List, Dict ,Literal
from pprint import pformat
import requests
from eolPCBComms import GpioSuite, I2CSuite
import pandas as pd
import pathlib
from scipy import signal
from scipy.signal import find_peaks
import re
from zebra import Zebra
from otoSprinkler import otoSprinkler
import pathlib
import numpy as np
import math
import tkinter as tk
import socket
import json
import matplotlib
matplotlib.use('Agg')   # needed to prevent multi-thread failures when using matplotlib
from matplotlib import pyplot as plt

class TestPeripherals:
    '''
    This class will sort the inputs into objects that have been predefined.
    Only one com port is supported, and the program won't run if more than one USB card is connected.
    '''
    def __init__(self, *args, **kwargs):
        for entry in args:
            if isinstance(entry, otoSprinkler):
                self.DUTsprinkler = entry
            elif isinstance(entry, GpioSuite):
                self.gpioSuite = entry
            elif isinstance(entry,I2CSuite):
                self.i2cSuite = entry
            else:
                raise TypeError("UNEXPECTED PROGRAM ERROR!")

    def add_device(self, new_object):
        "adds a new OtOSprinkler, GPIOSuite or I2CSuite class to TestPeriperals"
        if isinstance(new_object, otoSprinkler):
            self.DUTsprinkler = new_object
            # first remove PyOtO 2 from the module path sys.path, if it exists
            try:
                sys.path.remove(os.path.dirname(__file__) + "\pyoto2\otoProtocol")
            except:
                pass
            # add PyOtO to the module path sys.path
            sys.path.insert(0, os.path.dirname(__file__) + "\pyoto\otoProtocol")
            # remove duplicate entries from the module path sys.path
            sys.path = list(dict.fromkeys(sys.path))
            self.ClearModules()           
            import pyoto.otoProtocol.otoMessageDefs as otoMessageDefs
            import pyoto.otoProtocol.otoCommands as pyoto
            self.DUTMLB = pyoto.OtoInterface(pyoto.ConnectionType.UART, logger = None)
            self.DUTMLB.start_connection(port = None, reset_on_connect = True)
            self.DUTsprinkler.Firmware = self.DUTMLB.get_firmware_version().string
            if self.DUTsprinkler.Firmware < "v3":
                self.DUTMLB.stop_connection()
                # first remove PyOtO from the module path sys.path, if it exists
                try:
                    sys.path.remove(os.path.dirname(__file__) + "\pyoto\otoProtocol")
                except:
                    pass
                # add PyOtO2 to the module path sys.path
                sys.path.insert(0, os.path.dirname(__file__) + "\pyoto2\otoProtocol")
                # remove duplicate entries from the module path sys.path
                sys.path = list(dict.fromkeys(sys.path))
                self.ClearModules()   
                import pyoto2.otoProtocol.otoMessageDefs as otoMessageDefs
                import pyoto2.otoProtocol.otoCommands as pyoto
                self.DUTMLB = pyoto.OtoInterface(pyoto.ConnectionType.UART, logger = None)
                self.DUTMLB.start_connection(port = None, reset_on_connect = True)
            self.DUTsprinkler.SubscribeFrequency = pyoto.SensorSubscribeFrequencyEnum.SENSOR_SUBSCRIBE_FREQUENCY_100Hz
            self.DUTsprinkler.NoNVSException = pyoto.NotInitializedException
            self.DUTsprinkler.psig15 = otoMessageDefs.PressureSensorVersionEnum.MPRL_15_PSI_GAUGE.value
            self.DUTsprinkler.psig30 = otoMessageDefs.PressureSensorVersionEnum.MPRL_30_PSI_GAUGE.value                
            self.DUTsprinkler.macAddress = self.DUTMLB.get_mac_address().string
        elif isinstance(new_object, GpioSuite):
            self.gpioSuite = new_object
        elif isinstance(new_object, I2CSuite):
            self.i2cSuite = new_object
        else:
            raise TypeError("UNEXPECTED PROGRAM ERROR!")
        
    def ClearModules(self):
        "removes PyOtO modules from memory to allow switching between PyOtO versions"
        ModuleList = ["otoPacket", "otoMessageDefs", "otoCommands", "otoUart", "otoBle"]
        for ModuleName in ModuleList:
            try:
                del sys.modules[ModuleName]
            except:
                pass

class TestResult:
    "Abstract Class, can only be called when used with a specific test. This should have the most generic init and we can reinit more things in the child class."

    def __init__(self, test_status: Union[str, None], step_start_time: float = None):
        self.test_status = test_status
        self.step_start_time = step_start_time
        if self.step_start_time is None:
            self.cycle_time = None
        else:
            self.cycle_time = round(timeit.default_timer() - self.step_start_time, 4)

    @property
    def is_passed(self):
        if self.test_status is None:
            return True
        elif self.test_status[0] == "±":
            # when first character of the test message is ±, result information from a passed test can be displayed on the TKinter window.
            return True
        else:
            return False

    def __str__(self):
        return pformat(self.__dict__)

class TestStep:
    "Abstract base Class, can not be instantiated unless called with a child."

    def __init__(self, name: str, parent: tk):
        self.name = name
        self.parent = parent

    def run_step(self, peripherals_list: TestPeripherals):
        return

class TestSuite:
    '''There are two ways to run a test suite. One is through the gui. This will automatically hand the devices to you.
    The second way is to run it through the run_test_suite function. If running it through this method, the test devices must be created and handed ahead of time.'''

    def __init__(self, name: str, test_list: List[TestStep], test_devices: TestPeripherals, test_type: Literal ["EOL","Custom"]):
        self.name = name
        self.test_list = test_list
        self.test_devices = test_devices
        self.test_type = test_type  # if this is EOL, the test peripheral class is prepped differently.

    def run_test_suite(self, peripherals_list):
        "Runs through all of the test steps in the suite"
        test_result_list: List[TestResult] = list()
        for i, step in enumerate(self.test_list):
            test_result_list.append(step.run_step(peripherals_list = peripherals_list))
        return test_result_list

class CheckVacSwitch(TestStep):

    def run_step(self,peripherals_list:TestPeripherals):
        "Check if any of the vacuum switches are currently tripped"
        startTime = timeit.default_timer()
        pumpErrors: str = None
        if peripherals_list.gpioSuite.vacSwitchPin1.get() == 1:
            peripherals_list.DUTsprinkler.vacuumFail += 1
            pumpErrors = "Pump vacuum was not held on Bay 1 (black cap)"
        if peripherals_list.gpioSuite.vacSwitchPin2.get() == 1:
            peripherals_list.DUTsprinkler.vacuumFail += 2
            pumpErrors += "Pump vacuum was not held on Bay 2 (blue cap)"
        if peripherals_list.gpioSuite.vacSwitchPin3.get() == 1:
            peripherals_list.DUTsprinkler.vacuumFail += 4
            pumpErrors += "Pump vacuum was not held on Bay 3 (orange cap)"

        return CheckVacSwitchResult(test_status = pumpErrors, step_start_time = startTime)

class CheckVacSwitchResult(TestResult):
        def __init__(self, test_status: Union[str, None], step_start_time: float):
            super().__init__(test_status, step_start_time)

class EstablishLoggingLocation(TestStep):
    "class to log data files from the end of line test steps"
    TESTING_FOLDER = False  # set to true to store data in a different directory than production

    ERRORS = {"eolFixtureName":"EOL PCB hasn't been initalized with a vendor name and product name which we need to ID "
                               "the EOL fixture board and the location. It needs to be set up through the cypress "
                               "USB serial config utility",
              "pathIssue":"Multiple paths exist, can't decide which to write! Stop!"
              }

    def __init__(self, name: str, parent: tk, folder_name: str = None, csv_file_name: str = None, date_time: str = None):
        super().__init__(name, parent)
        self.folder_name = folder_name # aka the test step name
        self.csv_file_name = csv_file_name # sometimes non-standard
        self.date_time = date_time

    def run_step(self, peripherals_list: TestPeripherals):
        startTime = timeit.default_timer()
        if peripherals_list.DUTsprinkler.logFileDirectory is None:
            peripherals_list.DUTsprinkler.logFileDirectory = (pathlib.Path("C:\Data"))
            pathlib.Path(peripherals_list.DUTsprinkler.logFileDirectory).mkdir(parents = True, exist_ok = True)
            if self.TESTING_FOLDER == True:
                test_folder = "Test Folder"
                peripherals_list.DUTsprinkler.logFileDirectory = (pathlib.Path(peripherals_list.DUTsprinkler.logFileDirectory) / test_folder)
                pathlib.Path(peripherals_list.DUTsprinkler.logFileDirectory).mkdir(parents = True, exist_ok = True)
                
        if self.folder_name is not None:
            output_table_path = pathlib.Path(peripherals_list.DUTsprinkler.logFileDirectory/"Output") # Output Table Folder
            folder_path = pathlib.Path(output_table_path/str(self.folder_name)) # Test Step Name Folder
            unit_name_path = pathlib.Path(folder_path/str(peripherals_list.DUTsprinkler.deviceID)) # Device ID Folder Name
            if self.csv_file_name is None:
                file_path = pathlib.Path(unit_name_path/(self.date_time + ".csv"))
            else:
                file_path = pathlib.Path(unit_name_path/self.csv_file_name)

            pathlib.Path(output_table_path).mkdir(parents = True, exist_ok = True)
            pathlib.Path(folder_path).mkdir(exist_ok = True)
            pathlib.Path(unit_name_path).mkdir(exist_ok = True)
            return EstablishLoggingLocationResult(test_status = None, file_path = file_path, step_start_time = startTime)

class EstablishLoggingLocationResult(TestResult):

    def __init__(self, test_status: Union[str, None], file_path: Union[pathlib.Path,None], step_start_time: float = None):
        super().__init__(test_status, step_start_time)
        self.file_path = file_path

class PressureCheck(TestStep):
    "Reads pressure sensor for the number of seconds specified, used for Zero, Closed Valve and Fully Open tests"
    ERRORS:dict = {
                    "Timeout_V": "OtO valve failed to close in time.",
                    "Empty List": "No pressure information was received from OtO.",
                    "Bad_Function" : "UNEXPECTED PROGRAM ERROR!",
                    "High STD": "Pressure data is not consistent enough.",
                    "Low STD": "Pressure data is unusually consistent.",
                    "BAD_STD": "Pressure data is not within expected consistency limits.",
                    "BAD_Both": "Pressure data values and consistency are not within limits.",
                    "Pressure_Sensor": "OtO pressure sensor is not recognized."}

    def __init__(self, name: str, data_collection_time: int , class_function:str , valve_target: int, parent: tk):
        super().__init__(name, parent)
        self.data_collection_time = data_collection_time
        self.class_function = class_function
        self.valve_target = valve_target

    def run_step(self, peripherals_list: TestPeripherals):
        startTime = timeit.default_timer()
        pressure_sensor_check = int(peripherals_list.DUTMLB.get_pressure_sensor_version().pressure_sensor_version)

        if self.class_function in "EOL":  # new fully open test at closed positions uses same limits as zero pressure
            if pressure_sensor_check == peripherals_list.DUTsprinkler.psig15:
                max_acceptable_STD: float = 387.8  # Jan 2023 ±4σ
                min_acceptable_STD: float = 96.5  # Jan 2023 ±4σ
                max_acceptable_ADC: float = 1786755  # Jan 2023 ±4σ
                min_acceptable_ADC: float = 1611555  # Jan 2023 ±4σ
            elif pressure_sensor_check == peripherals_list.DUTsprinkler.psig30:
                max_acceptable_STD: float = 230  # Jan 2024 from histogram 230
                min_acceptable_STD: float = 66.5  # Jan 2023/4 66.5
                max_acceptable_ADC: float = 1875000  # Jan 2024 from histogram 1875000
                min_acceptable_ADC: float = 1520000  # Jan 2024 from histogram 1520000
            else:
                return PressureCheckResult(test_status=self.ERRORS.get("Pressure_Sensor"), step_start_time = startTime, Zero_P = mean, Zero_P_Tolerance = Zero_Tolerance)
        elif self.class_function in "MFO_test":  # new fully open test at closed positions uses adjusted limits
            if pressure_sensor_check == peripherals_list.DUTsprinkler.psig15:
                max_acceptable_STD: float = 780  # 2x limit from zero pressure
                min_acceptable_STD: float = 96.5  # Jan 2023 ±4σ
                max_acceptable_ADC: float = 2100000  # same as 30 psig value
                min_acceptable_ADC: float = 1611555  # Jan 2023 ±4σ
            elif pressure_sensor_check == peripherals_list.DUTsprinkler.psig30:
                max_acceptable_STD: float = 460  # 2x limit from zero pressure
                min_acceptable_STD: float = 66.5  # Jan 2023/4 66.5
                max_acceptable_ADC: float = 2100000  # from 2411 data
                min_acceptable_ADC: float = 1520000  # Jan 2024 from histogram 1520000
            else:
                return PressureCheckResult(test_status=self.ERRORS.get("Pressure_Sensor"), step_start_time = startTime, Zero_P = mean, Zero_P_Tolerance = Zero_Tolerance)
        elif self.class_function == "FO_test":
            if pressure_sensor_check == peripherals_list.DUTsprinkler.psig15:
                max_acceptable_STD: float = 32000  # confirmed Jan 2023
                min_acceptable_STD: float = 3000  # confirmed Jan 2023
                max_acceptable_ADC: float = 5861045  # updated Jan 2023
                min_acceptable_ADC: float = 4167230  # updated Jan 2023
            elif pressure_sensor_check == peripherals_list.DUTsprinkler.psig30:
                max_acceptable_STD: float = 12000  # updated Apr 2023
                min_acceptable_STD: float = 2000  # updated Apr 2023
                max_acceptable_ADC: float = 3790000  # updated Apr 2023
                min_acceptable_ADC: float = 2680000  # updated Apr 2023
            else:
                return PressureCheckResult(test_status=self.ERRORS.get("Pressure_Sensor"), step_start_time=startTime, Zero_P = mean, Zero_P_Tolerance = Zero_Tolerance)
        else:
            return PressureCheckResult(test_status=self.ERRORS.get("Bad_Function"), step_start_time = startTime, Zero_P = mean, Zero_P_Tolerance = Zero_Tolerance)

        standardDeviation:float = 32000  # should be equal or bigger than min_acceptable_STD defined above
        number_of_trials:int = 2
        trial_count:int = 1
        multiple_STD:int = 5
        Sensor_Read_List:list = []
        pressureReading:list = []
        pressureReadingData:list = []
        dataCount:int =0
        mean:int = 0
        maxDeviation:int = 0
        maxDeviation_x:int = 0
        Zero_Tolerance:int = 0
        setting_n_output: list = []
        Destination_Folder_1 = None
        loop_check:bool = True
        STD_check = True
        ADC_check = True

        peripherals_list.DUTMLB.use_moving_average_filter(True)
        while loop_check == True and trial_count <= number_of_trials:
            Sensor_Read_List:list = []
            output:list = []
            pressureReading:list = []
            pressureReadingData:list = []
            dataCount:int = 0
            mean:int = 0
            maxDeviation:int = 0
            maxDeviation_x:int = 0
            Zero_Tolerance:int = 0
            setting_n_output: list = []
            standardDeviation = 0

            peripherals_list.DUTMLB.set_sensor_subscribe(subscribe_frequency = peripherals_list.DUTsprinkler.SubscribeFrequency) 
            time.sleep(0.1)
            peripherals_list.DUTMLB.clear_incoming_packet_log()
            main_loop_start_time = time.perf_counter()
            while time.perf_counter() - main_loop_start_time <= self.data_collection_time:
                Sensor_Read_List.extend(peripherals_list.DUTMLB.read_all_sensor_packets(limit = None, consume = True))
            peripherals_list.DUTMLB.set_sensor_subscribe(subscribe_frequency = peripherals_list.DUTsprinkler.SubscribeOff)
            peripherals_list.DUTMLB.clear_incoming_packet_log()

            if not Sensor_Read_List:
                PressureCheckResult(test_status = self.ERRORS.get("Empty List"), step_start_time = startTime, Zero_P = None, Zero_P_Tolerance = None)

            for message in Sensor_Read_List:
                pressureReadingData.append([int(message.time_ms), int(message.pressure_adc)])
                pressureReading.append(int(message.pressure_adc))
                dataCount += 1

            mean = round(float(np.mean(pressureReading)), 0)
            standardDeviation = round(float(np.std(pressureReading)), 1)
            Zero_Tolerance = multiple_STD * standardDeviation
            for pressure in pressureReading:
                maxDeviation_x = maxDeviation
                maxDeviation = abs(mean-pressure)
                if maxDeviation <= maxDeviation_x: 
                    maxDeviation = maxDeviation_x

            output.append(mean)
            output.append(Zero_Tolerance)
            output.append(multiple_STD)
            
            if self.class_function == "EOL":
                peripherals_list.DUTsprinkler.ZeroPressure = output
                peripherals_list.DUTsprinkler.ZeroPressureAve = mean
                peripherals_list.DUTsprinkler.ZeroPressureSTD = standardDeviation
                function = "Calibrating Zero Pressure"
                self.parent.create_plot(window = self.parent.GraphHolder, plottype = "histplot", xaxis = pressureReading, yaxis = None, size = None, name = function, clear = False)
            elif self.class_function in "FO_test MFO_test":
                peripherals_list.DUTsprinkler.ZeroPressure_Temp = output
                function = "Valve Fully Open Position Testing"
                self.parent.create_plot(window = self.parent.GraphHolder, plottype = "fohistplot", xaxis = pressureReading, yaxis = None, size = None, name = function, clear = False)
            else: 
                return PressureCheckResult(test_status=self.ERRORS.get("Bad_Function"), step_start_time = startTime, Zero_P= mean, Zero_P_Tolerance= Zero_Tolerance)
          
            UnitName = peripherals_list.DUTsprinkler.deviceID
            bom_Number = peripherals_list.DUTsprinkler.bomNumber
            setting_n_output = ([f"Unit ID: {UnitName}", f"Mean: {mean}", f"STD: {standardDeviation}", f"Max Deviation to Mean: {maxDeviation}", f"Data Points: {dataCount}",
                                 f"{multiple_STD}x STD: {multiple_STD*standardDeviation}",f"Output List: {output} ", f"BOM Number: {bom_Number}" , f"Valve Target: {self.valve_target}" ,
                                 "Limits:",f" min and max ADC: [{min_acceptable_ADC} , {max_acceptable_ADC}]",f" min and max Std. Dev.: [{min_acceptable_STD} , {max_acceptable_STD}]"])

            setting_n_output = pd.DataFrame(setting_n_output)
            Data = pd.DataFrame(pressureReadingData)
            Data = Data.merge(setting_n_output, suffixes = ["_left", "_right"], left_index = True, right_index = True, how = "outer")
            Data.columns = ["Timestamp" , "Pressure Reading" , "More info"]
            Date_Time = str(datetime.now().strftime("%d-%m-%Y %H-%M-%S"))

            if self.class_function == "EOL":
                Destination_Folder_1 = "Zero P"
            elif self.class_function in "FO_test MFO_test":
                Destination_Folder_1 = "Fully Open"

            if UnitName != "":
                file_name = EstablishLoggingLocation(name = "CollectRawDataWithSubscribe", folder_name = Destination_Folder_1, date_time = Date_Time, parent = self.parent).run_step(peripherals_list = peripherals_list).file_path
                Data.to_csv(file_name, encoding = "utf-8")

            trial_count += 1
            if (standardDeviation <= max_acceptable_STD and standardDeviation >= min_acceptable_STD) and (mean <= max_acceptable_ADC and mean >= min_acceptable_ADC):
                loop_check = False

        if standardDeviation > max_acceptable_STD or standardDeviation < min_acceptable_STD:
            STD_check = False
        if mean > max_acceptable_ADC or mean < min_acceptable_ADC:
            ADC_check = False

        if not STD_check or not ADC_check:
            if not STD_check and not ADC_check:
                return PressureCheckResult(test_status = self.ERRORS.get("BAD_Both"), step_start_time = startTime, Zero_P = mean, Zero_P_Tolerance = Zero_Tolerance)
            if not STD_check:
                return PressureCheckResult(test_status = self.ERRORS.get("BAD_STD") + f"Set Min and Max: {min_acceptable_STD , max_acceptable_STD}, Measured STD: {standardDeviation}", step_start_time = startTime, Zero_P = mean, Zero_P_Tolerance = Zero_Tolerance)
            if not ADC_check: 
                return PressureCheckResult(test_status = f"Set Min and Max: {min_acceptable_ADC , max_acceptable_ADC}, Measured ADC: {mean}", step_start_time = startTime, Zero_P = mean, Zero_P_Tolerance = Zero_Tolerance)

        return PressureCheckResult(test_status = f"±Zero Pressure Reading: {mean:,} ADC, STD: {standardDeviation:,} ADC", step_start_time = startTime, Zero_P= mean, Zero_P_Tolerance= Zero_Tolerance)
            
class PressureCheckResult(TestResult):
    def __init__(self, test_status: Union[str, None], step_start_time: float, Zero_P:int, Zero_P_Tolerance:int):
        super().__init__(test_status, step_start_time)
        self.Zero_P = Zero_P
        self.Zero_P_Tolerance = Zero_P_Tolerance

class SendNozzleHome(TestStep):
    ERRORS: Dict[str,str] = {"Not Valid": "OtO nozzle position value is not valid."}

    def run_step(self, peripherals_list: TestPeripherals):
        startTime = timeit.default_timer()
        try:
            saved_MLB = int(peripherals_list.DUTMLB.get_nozzle_home_centidegrees().number)
        except peripherals_list.DUTsprinkler.NoNVSException:
            saved_MLB = 0
        except Exception as e:
            return SendNozzleHomeResult(test_status = str(e), step_start_time = startTime, N_Offset_calc = nozzleOffset, N_offset_MLB = new_saved_MLB)
        Nozzle_sensor_read = int(peripherals_list.DUTMLB.get_sensors().nozzle_position_centideg)
        if Nozzle_sensor_read > 36000 or Nozzle_sensor_read < 0:
            return SendNozzleHomeResult(test_status = self.ERRORS.get("NotValid") + f" at {Nozzle_sensor_read/100}°", step_start_time = startTime, N_Offset_calc = nozzleOffset, N_offset_MLB = new_saved_MLB)
        nozzleOffset = (saved_MLB + Nozzle_sensor_read) % 36000
        peripherals_list.DUTMLB.set_nozzle_home_centidegrees(nozzleOffset)
        peripherals_list.DUTsprinkler.nozzleOffset = nozzleOffset
        new_saved_MLB = int(peripherals_list.DUTMLB.get_nozzle_home_centidegrees().number)
        if new_saved_MLB == nozzleOffset:
            return SendNozzleHomeResult(test_status = f"±Nozzle Home Position: {nozzleOffset/100}°", step_start_time = startTime, N_Offset_calc = nozzleOffset, N_offset_MLB = new_saved_MLB)
        else:
            return SendNozzleHomeResult(test_status = f"OtO saved nozzle position {nozzleOffset/100}° doesn't match with computer value {new_saved_MLB/100}°.", step_start_time = startTime, N_Offset_calc = nozzleOffset, N_offset_MLB = new_saved_MLB)

class SendNozzleHomeResult(TestResult):
    def __init__(self, test_status: Union[str, None], step_start_time: float, N_Offset_calc: int,N_offset_MLB:int):
        super().__init__(test_status, step_start_time)
        self.N_Offset_calc = N_Offset_calc
        self.N_offset_MLB = N_offset_MLB

class NozzleRotationTestWithSubscribe(TestStep): 
    ERRORS: Dict[str,str] = {"Timeout_V": "Valve didn't reach target position in time.",
                            "Timeout_N": "Nozzle didn't reach target position in time.",
                            "Rotation_Rate": "Nozzle did not rotate at the correct speed.",
                            "EmptyList": "Nozzle position data was not received from OtO.",
                            "Data_colection_timeout": "Nozzle position data collection took too long.",
                            "Backwards": "Nozzle rotated backwards!",
                            "IDK": "Unexpected error during nozzle rotation!",
                            "Max_STD" : "Nozzle speed variation was too large.",
                            "Min_STD" : "Nozzle speed variation was unusually small."}
    TIMEOUT = 25 # in sec
    Nozzle_Duty_Cycle = 30
    MAXRotationSpeed: int = 3900  # Mar 2410/2411 data
    MINRotationSpeed: int = 2750  # Mar 2410/2411 data
    Max_STD = 345  # 2410/11 data
    Min_STD = 50  # 2410/11 data
    MAXNMotorCurrent = 95  # Dec 2023 data at Meco, first 141 units, confirmed with 2k units Jan 2024
    MINNMotorCurrent = 30  # 2410 data
    MAXNMotorCurrentSTD = 11.1  # 2410/2411 data
    MINNMotorCurrentSTD = 0.5  # 2410/2411 data

    def run_step(self, peripherals_list: TestPeripherals):
        startTime = timeit.default_timer()
        nozzle_rotation_test_failure_count = 0
        data_collection_status: int = None

        rawdata = self.Collecting_Nozzle_Rotation_Data(peripherals_list)
        # data_collection_status = 0 if all OK, 1 if List is empty, 2 if Timeout, 3 Unknown
        data_collection_status = rawdata.get("Status_Check")
        Nozzle_Rotation_Test_Data = rawdata.get("Collected_Data_List")
        # Timeout Locations: 0.5@ turning Nozzle around before start, 1@ Sending Nozzle Home, 2@ Opening the Valve, 3@ Sending Nozzle Back Home (After Data Gathering)
        # 4@ Closeing the Valve (After Data Gathering), 5@ test took longer than expected (i.e. nozzle stuck!)
        Timeout_Location = rawdata.get("TimeoutWhere")

        if data_collection_status == 0:
            dataPointsWithFailureCount = self.Nozzle_Rotation_Speed_Calculator(peripherals_list, Nozzle_Rotation_Test_Data)
            nozzle_rotation_test_failure_count = dataPointsWithFailureCount.get("Failure_Counter")
            nozzle_rotation_test_Max_STD_failure = dataPointsWithFailureCount.get("Max_STD_Limit")
            nozzle_rotation_test_Min_STD_failure = dataPointsWithFailureCount.get("Min_STD_Limit")
            Nozzle_Rotation_Test_Data = dataPointsWithFailureCount.get("Collected_Data_List")
            measured_average_speed = float(dataPointsWithFailureCount.get("Mean_Speed"))
            measured_STD = float(dataPointsWithFailureCount.get("Measured_STD"))
            peripherals_list.DUTsprinkler.nozzleRotationAve = round(measured_average_speed/100, 2)
            peripherals_list.DUTsprinkler.nozzleRotationSTD = round(measured_STD/100, 2)
            if "-v3" not in peripherals_list.DUTsprinkler.Firmware:
                if peripherals_list.DUTsprinkler.NozzleCurrentAve > self.MAXNMotorCurrent or peripherals_list.DUTsprinkler.NozzleCurrentAve < self.MINNMotorCurrent:
                    return NozzleRotationTestWithSubscribeResult(test_status = f"Nozzle motor current out of range! {self.MINNMotorCurrent}-{self.MAXNMotorCurrent}mA. Nozzle Rotation Speed: {round(measured_average_speed/100, 2)}°/sec, STD {round(measured_STD/100, 2)}°/sec, motor {peripherals_list.DUTsprinkler.NozzleCurrentAve} mA, STD {peripherals_list.DUTsprinkler.NozzleCurrentSTD} mA",
                    step_start_time = startTime, Friction_Points = nozzle_rotation_test_failure_count, Nozzle_Rotation_Data = Nozzle_Rotation_Test_Data)
                if peripherals_list.DUTsprinkler.NozzleCurrentSTD > self.MAXNMotorCurrentSTD or peripherals_list.DUTsprinkler.NozzleCurrentSTD < self.MINNMotorCurrentSTD:
                    return NozzleRotationTestWithSubscribeResult(test_status = f"Nozzle motor current variation too large! {self.MINNMotorCurrent}-{self.MAXNMotorCurrent}mA\n喷嘴电机电流变化过大!\nNozzle Rotation Speed 喷嘴旋转速度: {round(measured_average_speed/100, 2)}°/sec, STD {round(measured_STD/100, 2)}°/sec, motor 电机 {peripherals_list.DUTsprinkler.NozzleCurrentAve} mA, STD {peripherals_list.DUTsprinkler.NozzleCurrentSTD} mA",
                step_start_time = startTime, Friction_Points = nozzle_rotation_test_failure_count, Nozzle_Rotation_Data = Nozzle_Rotation_Test_Data)
            if self.MINRotationSpeed <= measured_average_speed <= self.MAXRotationSpeed and nozzle_rotation_test_Max_STD_failure == False and nozzle_rotation_test_Min_STD_failure == False:
                return NozzleRotationTestWithSubscribeResult(test_status = f"±Nozzle Rotation Speed 喷嘴旋转速度: {round(measured_average_speed/100, 2)}°/sec, STD {round(measured_STD/100, 2)}°/sec, motor 电机 {peripherals_list.DUTsprinkler.NozzleCurrentAve} mA, STD {peripherals_list.DUTsprinkler.NozzleCurrentSTD} mA",
                step_start_time = startTime, Friction_Points = nozzle_rotation_test_failure_count, Nozzle_Rotation_Data = Nozzle_Rotation_Test_Data)
            elif (measured_average_speed < self.MINRotationSpeed or measured_average_speed > self.MAXRotationSpeed) and nozzle_rotation_test_Max_STD_failure == True:
                return NozzleRotationTestWithSubscribeResult(test_status= f"Nozzle Rotation Speed 喷嘴旋转速度: {round(measured_average_speed/100, 2)}°/sec, STD {round(measured_STD/100, 2)}°/sec\n" + self.ERRORS.get("Max_STD") + " and...\n " + self.ERRORS.get("Rotation_Rate"), step_start_time = startTime,
                Friction_Points = nozzle_rotation_test_failure_count, Nozzle_Rotation_Data = Nozzle_Rotation_Test_Data) 
            elif (measured_average_speed < self.MINRotationSpeed or measured_average_speed > self.MAXRotationSpeed) and nozzle_rotation_test_Min_STD_failure == True:
                return NozzleRotationTestWithSubscribeResult(test_status= f"Nozzle Rotation Speed 喷嘴旋转速度: {round(measured_average_speed/100, 2)}°/sec, STD {round(measured_STD/100, 2)}°/sec\n" + self.ERRORS.get("Min_STD") + " and...\n " + self.ERRORS.get("Rotation_Rate"), step_start_time = startTime,
                Friction_Points = nozzle_rotation_test_failure_count, Nozzle_Rotation_Data = Nozzle_Rotation_Test_Data) 
            elif measured_average_speed < self.MINRotationSpeed or measured_average_speed > self.MAXRotationSpeed:
                return NozzleRotationTestWithSubscribeResult(test_status = f"Nozzle Rotation Speed 喷嘴旋转速度: {round(measured_average_speed/100, 2)}°/sec, STD {round(measured_STD/100, 2)}°/sec\n" + self.ERRORS.get("Rotation_Rate"), step_start_time = startTime,
                Friction_Points = nozzle_rotation_test_failure_count, Nozzle_Rotation_Data = Nozzle_Rotation_Test_Data)   
            elif nozzle_rotation_test_Max_STD_failure == True:
                return NozzleRotationTestWithSubscribeResult(test_status = f"Nozzle Rotation Speed 喷嘴旋转速度: {round(measured_average_speed/100, 2)}°/sec, STD {round(measured_STD/100, 2)}°/sec\n" + self.ERRORS.get("Max_STD"), step_start_time = startTime,
                Friction_Points = nozzle_rotation_test_failure_count, Nozzle_Rotation_Data = Nozzle_Rotation_Test_Data)  
            elif nozzle_rotation_test_Min_STD_failure == True:
                return NozzleRotationTestWithSubscribeResult(test_status = f"Nozzle Rotation Speed 喷嘴旋转速度: {round(measured_average_speed/100, 2)}°/sec, STD {round(measured_STD/100, 2)}°/sec\n" + self.ERRORS.get("Min_STD"), step_start_time = startTime,
                Friction_Points = nozzle_rotation_test_failure_count, Nozzle_Rotation_Data = Nozzle_Rotation_Test_Data)  
            else:
                return NozzleRotationTestWithSubscribeResult(test_status = f"Nozzle Rotation Speed 喷嘴旋转速度: {round(measured_average_speed/100, 2)}°/sec, STD {round(measured_STD/100, 2)}°/sec\n" + self.ERRORS.get("IDK"), step_start_time = startTime,
                Friction_Points = nozzle_rotation_test_failure_count, Nozzle_Rotation_Data = Nozzle_Rotation_Test_Data) 
        elif data_collection_status == 1:
            return NozzleRotationTestWithSubscribeResult(test_status=self.ERRORS.get("EmptyList"), step_start_time = startTime, Friction_Points = nozzle_rotation_test_failure_count, Nozzle_Rotation_Data = Nozzle_Rotation_Test_Data)
        elif data_collection_status == 2:
            return NozzleRotationTestWithSubscribeResult(test_status=self.ERRORS.get("Data_colection_timeout") + f" Failed at {Timeout_Location} ", step_start_time = startTime, Friction_Points = nozzle_rotation_test_failure_count, Nozzle_Rotation_Data = Nozzle_Rotation_Test_Data)
        elif data_collection_status == 5:
            return NozzleRotationTestWithSubscribeResult(test_status=self.ERRORS.get("Backwards"), step_start_time = startTime, Friction_Points = nozzle_rotation_test_failure_count, Nozzle_Rotation_Data = Nozzle_Rotation_Test_Data)
        else:
            return NozzleRotationTestWithSubscribeResult(test_status=self.ERRORS.get("IDK"), step_start_time = startTime, Friction_Points=nozzle_rotation_test_failure_count, Nozzle_Rotation_Data = Nozzle_Rotation_Test_Data)
        
    def Collecting_Nozzle_Rotation_Data(self, peripherals_list: TestPeripherals):
        startTime = timeit.default_timer()
        Sensor_Read_List: list = []
        Nozzle_Rotation_Data: list = []
        NozzleCurrent: list = []
        Nozzle_Home_Position = 0
        InitialAngularDelay = 1500 # in centideg
        check_stat: int = None # Will return 0 if all OK, 1 if List is empty, 2 if Timeout, 3 Unknown
     
        try:  # Sending Nozzle Home
            ReturnMessage = peripherals_list.DUTMLB.set_nozzle_position(Nozzle_Home_Position, wait_for_complete = True)
        except TimeoutError:
            return {"Status_Check": 2 , "TimeoutWhere": 1 , "Collected_Data_List": Nozzle_Rotation_Data}
        except Exception as e:
            self.parent.text_console_logger(str(e))
            return {"Status_Check": 3 , "TimeoutWhere": 1 , "Collected_Data_List": Nozzle_Rotation_Data}
        
        if ReturnMessage.message_type_string != "CTRL_OUT_COMMAND_COMPLETE":
            peripherals_list.DUTMLB.set_nozzle_duty(0, 0)
            return {"Status_Check": 2 , "TimeoutWhere": 1 , "Collected_Data_List": Nozzle_Rotation_Data}

        DataPointCounter = 0
        peripherals_list.DUTMLB.use_moving_average_filter(True)
        CurrentNozzlePosition = int(peripherals_list.DUTMLB.get_sensors().nozzle_position_centideg)
        StartPosition = (CurrentNozzlePosition + InitialAngularDelay) % 36000
        if StartPosition < CurrentNozzlePosition:  # StartPosition has to pass through 360° first before recording starts.
            FlipFirst = True
        else:  # StartPosition doesn't require passing through 360° before recording starts.
            FlipFirst = False

        Sensor_Read_List.clear()  # make sure list is empty
        NozzleCurrent.clear()  # make sure list is empty
        Recording = False
        RotationComplete = False
        Backwards = False
        # start nozzle motor turning at desired duty cycle        
        peripherals_list.DUTMLB.set_nozzle_duty(self.Nozzle_Duty_Cycle, 1)
        # turn on OtO data acquisition at 100Hz
        peripherals_list.DUTMLB.set_sensor_subscribe(subscribe_frequency = peripherals_list.DUTsprinkler.SubscribeFrequency)
        time.sleep(0.1)
        peripherals_list.DUTMLB.clear_incoming_packet_log()

        while (timeit.default_timer() - startTime) <= self.TIMEOUT and not RotationComplete:
            NozzleCurrent.extend([round(float(peripherals_list.DUTMLB.get_currents().nozzle_current_mA), 3)])
            read_all_sensor_outputs = peripherals_list.DUTMLB.read_all_sensor_packets(limit = None, consume = True)
            for ReadPoint in read_all_sensor_outputs:
                PreviousNozzlePosition = CurrentNozzlePosition
                CurrentNozzlePosition = int(ReadPoint.nozzle_position_centideg)
                if CurrentNozzlePosition < PreviousNozzlePosition:  # either rotating backwards or passed 360°
                    if np.sin(np.pi*PreviousNozzlePosition/18000) < 0:  # sine should be negative in previous position if passing 360°
                        if FlipFirst:
                            FlipFirst = False
                    else:  # if sine is positive and previous is greater than current position, the nozzle is turning backward so shut down data collection and rotation on the OtO, then error out.
                        RotationComplete = True
                        Backwards = True
                if Recording:
                    Sensor_Read_List.append(ReadPoint)
                    if not FlipFirst:
                        if CurrentNozzlePosition >= StartPosition:
                            RotationComplete = True
                            break
                elif not FlipFirst:  # now past 360°, so check for StartPosition to start recording
                    if CurrentNozzlePosition >= StartPosition:
                        Recording = True
                        FlipFirst = True

        # turn off OtO data acquisition
        peripherals_list.DUTMLB.set_sensor_subscribe(subscribe_frequency = peripherals_list.DUTsprinkler.SubscribeOff)
        peripherals_list.DUTMLB.clear_incoming_packet_log()
        # turn off nozzle rotation
        peripherals_list.DUTMLB.set_nozzle_duty(duty_cycle = 0, direction = 0, wait_for_complete = True)

        peripherals_list.DUTsprinkler.NozzleCurrentAve = round(float(np.average(NozzleCurrent)), 1)
        peripherals_list.DUTsprinkler.NozzleCurrentSTD = round(float(np.std(NozzleCurrent)), 2)

        Nozzle_Rotation_Data.clear()
        for sensor_message in Sensor_Read_List:
            timestamp = int(sensor_message.time_ms)
            Nozzle_Position = int(sensor_message.nozzle_position_centideg)
            Nozzle_Speed = int(sensor_message.nozzle_speed_centideg_per_sec)
            Nozzle_Rotation_Data.append([timestamp, Nozzle_Position, Nozzle_Speed])
            DataPointCounter += 1

        # End of Data Gathering; Sending Nozzle Back Home
        try:  
            ReturnMessage = peripherals_list.DUTMLB.set_nozzle_position(Nozzle_Home_Position, wait_for_complete = True)
        except TimeoutError as e:
            return {"Status_Check": 2,"TimeoutWhere": 3 , "Collected_Data_List": Nozzle_Rotation_Data}
        except Exception as e:
            self.parent.text_console_logger(str(e))
            return {"Status_Check": 3, "TimeoutWhere": 3 , "Collected_Data_List": Nozzle_Rotation_Data}

        if ReturnMessage.message_type_string != "CTRL_OUT_COMMAND_COMPLETE":
            self.parent.text_console_logger(ReturnMessage.message_type_string)
            return {"Status_Check": 2 , "TimeoutWhere": 3 , "Collected_Data_List": Nozzle_Rotation_Data}

        # data_collection_status = 0 if all OK, 1 if List is empty, 2 if Timeout, 3 Unknown, 5 backwards rotation
        if Nozzle_Rotation_Data and RotationComplete: 
            check_stat = 0
            timeout_pos = None
        elif not Nozzle_Rotation_Data: 
            check_stat = 1
            timeout_pos = None
        elif not RotationComplete:
            check_stat = 2
            timeout_pos = 5
        elif Backwards:
            check_stat = 5
            timeout_pos = None
        else:
            check_stat = 3
            timeout_pos = None
        return {"Status_Check": check_stat, "TimeoutWhere": timeout_pos, "Collected_Data_List": Nozzle_Rotation_Data}

    def Nozzle_Rotation_Speed_Calculator(self, peripherals_list: TestPeripherals, Nozzle_Rotation_Data: list): 
        Failed_Speed_counter:int = 0
        Max_Delta_Position: int = 100  # error count if more than this number of centidegrees between readings.
        number_of_data_points:int = 0
        Average_Speed: float = 0
        Delta_Speed: int = 0
        Max_Difference: int = 0
        Nozzle_Position: int = 0
        Delta_Position: int = 0
        Delta_Position_Counter: int = 0
        Speed_settings: list = []
        dataSet: list = []
        Speed_List: list = []
        max_speed_recorded = 0
        speed_standard_deviation: float = 0
        Max_STD_Check: bool = True
        Min_STD_Check: bool = True
        Mean_Rotation_Speed = (self.MAXRotationSpeed + self.MINRotationSpeed) *0.5
        Tolerance_Rotation_Speed = (self.MAXRotationSpeed - self.MINRotationSpeed) *0.5
        
        for data_point in Nozzle_Rotation_Data:
            if data_point[2] >= max_speed_recorded:
                max_speed_recorded = data_point[2]

        for dataSet in Nozzle_Rotation_Data:
            Rotation_Rate = dataSet[2]
            Delta_Speed = Mean_Rotation_Speed - Rotation_Rate
            
            if number_of_data_points > 0:
                if 0 <= Nozzle_Position <= 9000:
                    if 27000 <= dataSet[1] <= 36000:
                        Delta_Position = -(36000 - dataSet[1] + Nozzle_Position)
                    else:
                        Delta_Position = dataSet[1] - Nozzle_Position
                elif 27000 <= Nozzle_Position <=36000:
                    if 0 <= dataSet[1] <= 9000:
                        Delta_Position = 36000 - Nozzle_Position + dataSet[1]
                    else:
                        Delta_Position = dataSet[1] - Nozzle_Position
                else:
                    Delta_Position = dataSet[1] - Nozzle_Position                    
                Nozzle_Position = dataSet[1]
            else:
                Nozzle_Position = dataSet[1]
                Delta_Position = 0

            if abs(Delta_Position) >= Max_Delta_Position:
                Delta_Position_Counter += 1

            if abs(Delta_Speed) > abs(Max_Difference):
                Max_Difference = Delta_Speed

            if abs(Delta_Speed) > Tolerance_Rotation_Speed:
                Failed_Speed_counter += 1

            unit_radius = round(Rotation_Rate / max_speed_recorded, 4)
            x_position = round(unit_radius * math.cos(math.radians(Nozzle_Position/100)), 4)
            y_position = round(unit_radius * math.sin(math.radians(Nozzle_Position/100)), 4)

            Speed_List.append(Rotation_Rate)

            dataSet.append(Failed_Speed_counter)
            dataSet.append(Delta_Speed)
            dataSet.append(Delta_Position)
            dataSet.append(unit_radius)
            dataSet.append(x_position)
            dataSet.append(y_position)

            number_of_data_points +=1

        speed_standard_deviation = round(float(np.std(Speed_List)), 1)
        Average_Speed = round(float(np.mean(Speed_List)), 1)

        if self.Min_STD <= speed_standard_deviation <= self.Max_STD:
            Max_STD_Check = False
            Min_STD_Check = False
        elif speed_standard_deviation > self.Max_STD:
            Max_STD_Check = True
        else:
            Min_STD_Check = True

        UnitName = peripherals_list.DUTsprinkler.deviceID
        bom_Number = peripherals_list.DUTsprinkler.bomNumber
        Speed_settings = ([ f"Unit ID: {UnitName}", f"Set Mean: {Mean_Rotation_Speed}", f"Set Tolerance: {Tolerance_Rotation_Speed}",
                            f"Set Motor Duty Cycle: {self.Nozzle_Duty_Cycle}", f"Set Max STD: {self.Max_STD}", f"Set Min STD: {self.Min_STD}", f"Average Speed: {Average_Speed}",
                            f"Measured Speed STD: {speed_standard_deviation}", f"Max Difference to set Mean: {Max_Difference}", f"Nummber of Failed Points: {Failed_Speed_counter}",
                            f"Max Delta Position Set (Between adjacent points): {Max_Delta_Position}",
                            f"Delta Position Counter (Exceeded Set Max): {Delta_Position_Counter}", f"Max Speed Recorded: {max_speed_recorded}", f"BOM Number: {bom_Number}"])
        Speed_settings = pd.DataFrame(Speed_settings)
        Data = pd.DataFrame(Nozzle_Rotation_Data)
        peripherals_list.DUTsprinkler.nozzleRotationData = Nozzle_Rotation_Data

        Data = Data.merge(Speed_settings, suffixes = ['_left', '_right'], left_index = True, right_index = True, how = 'outer')
        Data.columns = ["Time Stamp", "Nozzle Position", "Nozzle Speed", "Failure Sequence", "Delta Speed (to Set Mean)", "Delta Position (adjacent points)", "R (Normalized Speed)" , "X" , "Y" , "Setting Info"]

        RotationalSpeed = Data["Nozzle Speed"]
        RotationalSpeed = list(map(lambda v: v/100, RotationalSpeed))
        RotationalPosition = Data["Nozzle Position"]
        RotationalPosition = list(map(lambda a: -a/18000*np.pi, RotationalPosition))
        self.parent.create_plot(window = self.parent.GraphHolder, plottype = "polar", xaxis = RotationalPosition, yaxis = RotationalSpeed, size = None, name = "Nozzle Rotation 喷嘴旋转测试", clear = True)

        Date_Time = str(datetime.now().strftime("%d-%m-%Y %H_%M_%S"))
        if peripherals_list.DUTsprinkler.deviceID != "":
            file_name= EstablishLoggingLocation(name = "NRT", folder_name = "Nozzle Rotation", csv_file_name = f"{self.Nozzle_Duty_Cycle}DC_{Date_Time}.csv", date_time = Date_Time, parent = self.parent).run_step(peripherals_list=peripherals_list).file_path
            Data.to_csv(file_name, encoding='utf-8')

        return_dict = {"Failure_Counter": Failed_Speed_counter , "Max_STD_Limit": Max_STD_Check , "Min_STD_Limit": Min_STD_Check,
                        "Collected_Data_List": Nozzle_Rotation_Data, "Mean_Speed":Average_Speed, "Measured_STD": speed_standard_deviation}
        return return_dict

class NozzleRotationTestWithSubscribeResult(TestResult):
    def __init__(self, test_status: Union[str, None], step_start_time: float , Friction_Points:int, Nozzle_Rotation_Data:list ):
        super().__init__(test_status, step_start_time)
        self.Friction_Points = Friction_Points
        self.Nozzle_Rotation_Data = Nozzle_Rotation_Data

class GetUnitName(TestStep):
    ERRORS: dict = {"Cloud Failed": "OtO unit name function failed.",
                    "Blank BOM": "OtO computer doesn't have a BOM, can't be tested.",
                    "Can't Write": "Error writing BOM to OtO.",
                    "No Device ID": "OtO doesn't have a unit name, won't check Firebase"}

    def run_step(self, peripherals_list: TestPeripherals):
        startTime = timeit.default_timer()
        Firmware = peripherals_list.DUTsprinkler.Firmware
        self.parent.labelFirmware.configure(text = Firmware)
        self.parent.labelFirmware.update()
        # If there isn't a BOM stop and error out
        try:
            peripherals_list.DUTsprinkler.bomNumber = peripherals_list.DUTMLB.get_device_hardware_version().string
        except Exception as e:
            return GetUnitNameResult(test_status = self.ERRORS.get("Blank BOM") + str(e), step_start_time = startTime)
        # Update the BOM displayed on the screen
        existingBOM = peripherals_list.DUTsprinkler.bomNumber
        self.parent.text_bom_number.delete(1.0,tk.END)
        self.parent.text_bom_number.insert(tk.END, existingBOM)
        self.parent.text_bom_number.update()
        # check for an existing unit name on the board. If there isn't one just use the MAC address.
        try:
            existingSerial = peripherals_list.DUTMLB.get_device_id().string
            if len(existingSerial) == 0:
                existingSerial = None
        except Exception as e:
            return GetUnitNameResult(test_status = self.ERRORS.get("No Device ID") + str(e), step_start_time = startTime)
        
        if existingSerial != None:
            ReturnMessage = self.otoGenerateSerialRequest(peripherals_list = peripherals_list, existingSerial = existingSerial)
            if ReturnMessage != None:
                return GetUnitNameResult(test_status = ReturnMessage, step_start_time = startTime)
        existingSerial = peripherals_list.DUTsprinkler.deviceID
        self.parent.text_device_id.delete(1.0, tk.END)
        self.parent.text_device_id.insert(tk.END, existingSerial)
        self.parent.text_device_id.update()
        if len(existingSerial) != 0: #blank units will have "" as the default value
            if existingSerial[0:3] == "oto" and len(existingSerial) == 10 and existingSerial[3:10].isnumeric():  # is the Device ID valid?
                EstablishLoggingLocation(name = None, folder_name = None, csv_file_name = None, parent = self.parent).run_step(peripherals_list = peripherals_list)
                self.parent.text_console_logger(f"{existingSerial}, {existingBOM}, {peripherals_list.DUTsprinkler.macAddress}")
                return GetUnitNameResult(test_status = None, step_start_time = startTime)
            else: # Invalid unit name
                return GetUnitNameResult(test_status = f"Invalid unit name 洒水器产品号无效: {existingSerial}", step_start_time = startTime)                
        else:
            return GetUnitNameResult(test_status = self.ERRORS.get("No Device ID"), step_start_time = startTime)
        
    def otoGenerateSerialRequest(self, peripherals_list: TestPeripherals, existingSerial: str = None):
        "Send HTTP request to oto-generate-unit function, optionally using given unit name. Args: existingSerial (optional): given unit name if required. Returns: None if OK, otherwise error as String"
        if "OTO" in peripherals_list.DUTsprinkler.factoryLocation.upper():
            factory_location = "OTO_MFG"
        else:
            factory_location = "MECO_MFG"
        # oto_generate_unit_url = "https://us-central1-oto-test-3254b.cloudfunctions.net/masterGenerateUnit"
        oto_generate_unit_url = 'https://meco-accessor-service-ugegz6xfpa-pd.a.run.app/oto/meco/masterGenerateUnit'
        requestJson = {
            "key": "XJhbCu4ujfJF3Ugu",
            "bomNumber": peripherals_list.DUTsprinkler.bomNumber,
            "batchNumber": peripherals_list.DUTsprinkler.batchNumber,
            "macAddress": peripherals_list.DUTsprinkler.macAddress,
            "flashFactoryLocation": factory_location
        }
        if existingSerial is not None:
            requestJson["unitSerial"] = existingSerial
        try:
            self.parent.text_console_logger("Cloud communication...  正在连接云服务器…")            
            response = requests.post(oto_generate_unit_url, json = requestJson, timeout = 10, allow_redirects = False)
        except requests.exceptions.ConnectTimeout as error:
            return f"Can't connect to Firebase website  无法连接数据库网站\n{oto_generate_unit_url}"
        except requests.exceptions.ConnectionError as error:
            return f"Can't connect to Firebase website  无法连接数据库网站\n{oto_generate_unit_url}"
        except Exception as error:
            return f"Unknown HTTP Request Exception  未知HTTP请求异常:\n{repr(error)}"
        # Parse response body as a JSON
        try:
            responseJson = response.json()
        except json.JSONDecodeError:
            return response.content.decode()
        except Exception:
            return "Unknown exception during JSON response parse  JSON响应解析异常"
        # Check response, return error message if not
        if response.status_code == 200:
            # Retrieve the response
            try:
                newserial = str(responseJson["unitSerial"])
                peripherals_list.DUTsprinkler.deviceID = newserial
                if existingSerial is None:
                    self.parent.text_console_logger(f"Generated unit name 已生成产品号: {peripherals_list.DUTsprinkler.deviceID}, writing to OtO... 存储到OtO...")
            except Exception as error:
                return f"Unable to read JSON field in POST response  无法在云服务器中读取JSON字段:\n{repr(error)}"
        else:
            ErrorMessage = json.loads(response.content.decode())["error"]
            if "Firebase found one unit with this MAC address but it does not match the device ID provided. Firebase: oto" in ErrorMessage:
                newserial = ErrorMessage[102:112]
                if newserial[0:3] != "oto" or not newserial[3:10].isnumeric() or len(newserial) != 10 or existingSerial != None:
                    return ErrorMessage
                else:
                    self.parent.text_console_logger(f"Updated unit name to match Firebase! 产品编号已更新，以匹配 Firebase! {peripherals_list.DUTsprinkler.deviceID}, writing to OtO... 存储到OtO...")
            else:
                return ErrorMessage
        if existingSerial is None:
            try:
                peripherals_list.DUTMLB.set_device_id(newserial)
            except Exception as f:
                return f"Unable to write unit name to OtO  无法把产品号写入洒水器: {newserial}"
            try:
                peripherals_list.DUTsprinkler.deviceID = peripherals_list.DUTMLB.get_device_id().string
            except Exception as f:
                return f"Didn't write unit name to OtO!  未把产品号写入洒水器  {newserial}"
            if peripherals_list.DUTsprinkler.deviceID != newserial:
                return f"Unit names don't match!  产品号与洒水器不符  OtO: {peripherals_list.DUTsprinkler.deviceID}, Cloud: {newserial}"
        else:
            self.parent.text_console_logger(f"Matched unit name with Firebase  已与数据库匹配产品号: {newserial}")            
        return None
    
class GetUnitNameResult(TestResult):
    def __init__(self, test_status, step_start_time):
        super().__init__(test_status, step_start_time)

class TestBattery(TestStep):
    PASS_VOLTAGE:float = 3.5 #4.2V is full, based on stats of 141 units Dec 2023 at Meco
    ERRORS: Dict[str,str] = {"Low Battery": "Charge battery before retesting.  重新测试前，先给电池充电",
                         "No Reading": "Error reading battery voltage.  电池电压读取错误"
                         }

    def run_step(self, peripherals_list: TestPeripherals):
        startTime = timeit.default_timer()
        battVoltage = round(float(peripherals_list.DUTMLB.get_voltages().battery_voltage_v), 3)
        peripherals_list.DUTsprinkler.batteryVoltage = battVoltage
        if battVoltage < self.PASS_VOLTAGE:
            return TestBatteryResult(test_status = self.ERRORS.get("Low Battery") + f"({battVoltage}V)\n", actual_voltage = battVoltage, step_start_time= startTime, pass_criteria = self.PASS_VOLTAGE)
        elif battVoltage == 0:
            return TestBatteryResult(test_status=self.ERRORS.get("No Reading"), actual_voltage = battVoltage, step_start_time = startTime, pass_criteria = self.PASS_VOLTAGE)
        return TestBatteryResult(test_status = f"±Battery  电池电压: {battVoltage}V", step_start_time = startTime, actual_voltage = battVoltage, pass_criteria = self.PASS_VOLTAGE)

class TestBatteryResult(TestResult):
    def __init__(self, pass_criteria: float, actual_voltage: float, test_status,step_start_time):
        super().__init__(test_status, step_start_time)
        self.pass_criteria = pass_criteria
        self.actual_voltage = actual_voltage

class TestExternalPower(TestStep):
    PASS_VOLTAGE: float = 10.667  # Jan 2023 update ±4σ
    MAX_VOLTAGE: float = 12.623  # Jan 2023 update ±4σ
    PASS_CURRENT: float = 0.337  # Jan 2023 update ±4σ
    MAX_CURRENT: float =  0.385  # Jan 2023 update ±4σ
    PASS_CURRENTv4 = 0.37  # Based on "calibrated" current results
    MAX_CURRENTv4 =  0.43  # Based on "calibrated" current results
    ERRORS: Dict[str, str] = {
        "Current Below": "External charging current BELOW limit.  外部充电电流低于极限值",
        "Current Above": "External charging current ABOVE limit.  外部充电电流高于极限值"
        }

    def run_step(self, peripherals_list: TestPeripherals):
        startTime = timeit.default_timer()
        ErrorAfterMeasurement = False
        if peripherals_list.DUTsprinkler.testFixtureName == "MecoChina1":
            CurrentFactor = 0.835
        elif peripherals_list.DUTsprinkler.testFixtureName == "MecoChina2":
            CurrentFactor = 0.955
        elif peripherals_list.DUTsprinkler.testFixtureName == "MecoChina3":
            CurrentFactor = 0.969
        elif peripherals_list.DUTsprinkler.testFixtureName == "MecoChina4":
            CurrentFactor = 0.967
        elif peripherals_list.DUTsprinkler.testFixtureName == "MecoChina5":
            CurrentFactor = 0.96
        elif peripherals_list.DUTsprinkler.testFixtureName == "OTOLab1":
            CurrentFactor = 0.764
        else:
            CurrentFactor = 1
            ErrorAfterMeasurement = True

        if not hasattr(peripherals_list, "gpioSuite"):
            new_gpio = GpioSuite()
            peripherals_list.add_device(new_object = new_gpio)
        if not hasattr(peripherals_list, "i2cSuite"):
            new_i2c = I2CSuite()
            peripherals_list.add_device(new_object = new_i2c)        
        Result = peripherals_list.gpioSuite.extPowerPin.set(0) #turn on power
        PowerTimeStart = time.perf_counter()
        Success = 1
        while time.perf_counter() - PowerTimeStart < 2 and Success == 1:
            time.sleep(0.2)
            Success = peripherals_list.gpioSuite.extPowerPin.get()
        if Success == 1:
            print(Result)
            return TestExternalPowerResult(test_status = "Can't turn on external power!  无法打开外部电源", step_start_time = startTime, pass_criteria = (self.PASS_VOLTAGE, self.PASS_CURRENT), actual_readings = (0, 0))            
        time.sleep(1)
        chargingVoltage = round(float(peripherals_list.DUTMLB.get_voltages().solar_voltage_v), 3)
        chargingCurrent = round(float(peripherals_list.i2cSuite.i2cLTC2945.get_current() * CurrentFactor), 3)
        peripherals_list.DUTsprinkler.extPowerCurrent = chargingCurrent
        peripherals_list.DUTsprinkler.extPowerVoltage = chargingVoltage

        Result = peripherals_list.gpioSuite.extPowerPin.set(1) #turn off power
        time.sleep(0.1)

        if peripherals_list.gpioSuite.extPowerPin.get() != 1:
            print(Result)
            return TestExternalPowerResult(test_status = "Can't turn off external power!  无法关闭外部电源", step_start_time = startTime, pass_criteria = (self.PASS_VOLTAGE, self.PASS_CURRENT), actual_readings = (chargingVoltage, chargingCurrent))

        if ErrorAfterMeasurement:
            return TestExternalPowerResult(test_status = f"[{chargingCurrent}A.] Must calibrate current on this new EOL board first!\n必须首先校准这个新的EOL板上的电流!\n{peripherals_list.DUTsprinkler.testFixtureName}", step_start_time = startTime, pass_criteria = (self.PASS_VOLTAGE, self.PASS_CURRENT), actual_readings = (0, 0))

        battery_voltage = peripherals_list.DUTsprinkler.batteryVoltage
        if battery_voltage >= 4.0:  # if battery charge is high, the lower limit of current can be dramatically affected, so update the limit
            self.PASS_CURRENT = 0.00
            self.PASS_CURRENTv4 = 0.03

        if self.PASS_CURRENTv4 <= chargingCurrent <= self.MAX_CURRENTv4:
            return TestExternalPowerResult(test_status = f"±Charging 充电中: {chargingCurrent}A" , step_start_time = startTime, pass_criteria = (self.PASS_VOLTAGE, self.PASS_CURRENTv4), actual_readings = (chargingVoltage, chargingCurrent))
        elif chargingCurrent < self.PASS_CURRENTv4:
            return TestExternalPowerResult(test_status = self.ERRORS.get("Current Below") + f" {chargingCurrent}A", step_start_time = startTime, pass_criteria = (self.PASS_VOLTAGE, self.PASS_CURRENTv4), actual_readings = (chargingVoltage, chargingCurrent))
        elif chargingCurrent > self.MAX_CURRENTv4:
            return TestExternalPowerResult(test_status = self.ERRORS.get("Current Above") + f" {chargingCurrent}A", step_start_time = startTime, pass_criteria = (self.PASS_VOLTAGE, self.PASS_CURRENTv4), actual_readings = (chargingVoltage, chargingCurrent))

class TestExternalPowerResult(TestResult):
    def __init__(self, actual_readings: tuple[float,float], pass_criteria: tuple[float,float], test_status, step_start_time):
        super().__init__(test_status, step_start_time)
        self.actual_readings = actual_readings
        self.pass_criteria = pass_criteria

class TestMoesFullyOpen(TestStep):

    def run_step(self, peripherals_list: TestPeripherals):
        target = 9000  # nominal open in centidegrees
        tolerance = 5650  # nominal movement to closed from target in centidegrees
        AdjustmentFactor = 25  # factor used to move angle, the square root of pressure ADC difference divided by this factor x 1°, when adjusting the zero position
        SpanTolerance = 500  # acceptance tolerance between the two pressure ADC values, 2411 data
        SigmaSpanTolerance = 80  # acceptance σ tolerance between the two pressure ADC sigmas. 2411 data
        startTime = timeit.default_timer()
        Finished = False
        if not hasattr(peripherals_list, "gpioSuite"): # if called by itself by one button press
            new_gpio = GpioSuite()
            peripherals_list.add_device(new_object = new_gpio)
        Targets = [0, 1, 2]  # Not using 0
        Targets[1] = (target + (36000 - tolerance)) % 36000  # typically will equal 3350 centidegrees
        Targets[2] = (target + tolerance) % 36000  # typically will equal 14650 centidegrees
        pressure_reading_list = None
        average_pressure = None
        standard_deviation = None
        dataCollectionTime = 2.1
        MaxRepeats = 3  # number of chances to adjust the zero
        Repeats = 1  # current count of trials
        while Repeats <= MaxRepeats:
            plt.figure(2)
            plt.close()  # clear the histogram memory for fully open
            Finished = False
            CurrentTarget = 1
            while not Finished:
                peripherals_list.DUTsprinkler.valveFullyOpenTrials = Repeats
                ReturnMessage = peripherals_list.DUTMLB.set_valve_position(valve_position_centideg = Targets[CurrentTarget], wait_for_complete = True)
                if ReturnMessage.message_type_string != "CTRL_OUT_COMMAND_COMPLETE":
                    return TestMoesFullyOpenResult(test_status = str(f"OtO valve did not move to {round(Targets[CurrentTarget]/100, 2)}° in time.\n洒水器阀门未及时移动到目标位置"), step_start_time = startTime)
                peripherals_list.DUTsprinkler.ZeroPressure_Temp.clear()
                peripherals_list.gpioSuite.airSolenoidPin.set(0) # turn on air
                time.sleep(0.3)  # give some time to build pressure
                result = PressureCheck(name = "Fully Open Test 阀门全打开测试", data_collection_time = dataCollectionTime , class_function= "MFO_test" , valve_target = target, parent = self.parent).run_step(peripherals_list)
                peripherals_list.gpioSuite.airSolenoidPin.set(1) # turn off air
                if peripherals_list.DUTsprinkler.ZeroPressure_Temp:
                    pressure_reading_list = peripherals_list.DUTsprinkler.ZeroPressure_Temp
                    average_pressure = pressure_reading_list[0]
                    standard_deviation = pressure_reading_list[1]/pressure_reading_list[2]
                    if CurrentTarget == 1:
                        peripherals_list.DUTsprinkler.valveFullyOpen1Ave = average_pressure
                        peripherals_list.DUTsprinkler.valveFullyOpen1STD = standard_deviation
                        CurrentTarget = 2
                    elif CurrentTarget == 2:
                        peripherals_list.DUTsprinkler.valveFullyOpen3Ave = average_pressure
                        peripherals_list.DUTsprinkler.valveFullyOpen3STD = standard_deviation
                        Finished = True
                if result.test_status != None and result.test_status[0] != "±":
                    return TestMoesFullyOpenResult(f"{round(Targets[CurrentTarget-1]/100, 2)}° pressure reading not within specification. " + result.test_status +"\n点压力读数不在规定范围内", step_start_time = startTime)
            Span = peripherals_list.DUTsprinkler.valveFullyOpen1Ave - peripherals_list.DUTsprinkler.valveFullyOpen3Ave
            SigmaSpan = abs(peripherals_list.DUTsprinkler.valveFullyOpen1STD - peripherals_list.DUTsprinkler.valveFullyOpen3STD)
            if abs(Span) < SpanTolerance and SigmaSpan < SigmaSpanTolerance:
                ReturnMessage = peripherals_list.DUTMLB.set_valve_position(wait_for_complete = False, valve_position_centideg = 0)
                return TestMoesFullyOpenResult(test_status = None, step_start_time = startTime)
            else:
                try:
                    saved_MLB = int(peripherals_list.DUTMLB.get_valve_home_centidegrees().number) #this is abs
                except peripherals_list.DUTsprinkler.NoNVSException:
                    saved_MLB = 0
                except Exception as e:
                    return str(e)
                DeltaAngle = int(np.sign(Span) * -100 * math.sqrt(abs(Span)) / AdjustmentFactor)
                if DeltaAngle > 200:
                    DeltaAngle = 200
                if DeltaAngle < -200:
                    DeltaAngle = -200
                if DeltaAngle < 0:
                    DeltaAngle = 36000 + DeltaAngle
                valve_Offset = (DeltaAngle + saved_MLB) % 36000 # this makes it absolute
                absolute_fully_open = (valve_Offset + 9000) % 36000
                peripherals_list.DUTMLB.set_valve_home_centidegrees(int(valve_Offset)) # we write the absolute value back to the MLB
                peripherals_list.DUTsprinkler.valveOffset = int(valve_Offset)
                peripherals_list.DUTsprinkler.valveFullyOpen = int(absolute_fully_open)
                self.parent.text_console_logger(f"Revised Absolute Valve Closed: {valve_Offset/100}°, Open: {absolute_fully_open/100}°, {DeltaAngle/100}")
                fw_ValveOffset = int(peripherals_list.DUTMLB.get_valve_home_centidegrees().number)
                memory_ValveOffset = peripherals_list.DUTsprinkler.valveOffset
                if fw_ValveOffset != memory_ValveOffset:
                    return TestMoesFullyOpenResult(test_status = f"OtO's saved valve position {fw_ValveOffset/100}° does not match computer value {memory_ValveOffset/100}°.", step_start_time = startTime)
                Repeats += 1
        ReturnMessage = peripherals_list.DUTMLB.set_valve_closed()
        return TestMoesFullyOpenResult(test_status = f"Failed Fully Open Test {Span}", step_start_time = startTime)
        
class TestMoesFullyOpenResult(TestResult):

    def __init__(self, test_status: Union[str, None], step_start_time: float = None):
        super().__init__(test_status, step_start_time)

class TestPump(TestStep):
    '''
    these switches are normally closed so 0 indicates that the switch triggered due to vacuum at the switch
    '''
    PASS_TIME:float = 5.608  # based on BPT pumps, 2k sample, ±4σ
    TIMEOUT:float = 5.608
    PING_TIME:float = 8.0 # it will never ping now since we expect it to pass within 5 seconds.
    SI_UNITS:str = "s"
    ERRORS: Dict[str,str] = {"No Pumps": "OtO pump failed.  洒水器蠕动泵失效",
                             "Wrong Pump": "Wrong OtO pump ran, tear down unit to check hose and wiring connections.\n洒水器蠕动泵运行错误, 把洒水器拆下来, 检查水管是否连接正确, 接线是否正确\n",
                             "Invalid Target Pump": "Target pump must be 1, 2 or 3"
                             }
    DEFAULT_PUMP_DUTY = 100
    CAPS: str = "Black", "Blue", "Orange"
    CAPSC: str = "黑", "蓝", "橘"

    def __init__(self, target_pump: int, name: str, parent: tk, target_pump_duty = None):
        super().__init__(name, parent)
        self.target_pump = target_pump
        self.user_ping = False
        if target_pump_duty is None:
            self.target_pump_duty = self.DEFAULT_PUMP_DUTY
        else:
            self.target_pump_duty = target_pump_duty

    def run_step(self, peripherals_list: TestPeripherals):
        startTime = timeit.default_timer()
        PumpCurrent = []
        Firmware = peripherals_list.DUTsprinkler.Firmware

        if Firmware < "v3" or (not "-v4" in Firmware and not "-v5" in Firmware):
            UseSubscribe = False
        else:
            UseSubscribe = True

        UseSubscribe = False  # Can't get pump subscribe to work consistently on EOL, randomly see unknown program errors during pump test

        if self.target_pump == 1 or self.target_pump == 2 or self.target_pump == 3:
            if UseSubscribe:
                # turn on OtO data acquisition at 100Hz
                ReturnMessage = peripherals_list.DUTMLB.set_sensor_subscribe(subscribe_frequency = peripherals_list.DUTsprinkler.SubscribeFrequency)
                time.sleep(0.1) # to ignore first few filtered pressure values
            ReturnMessage = peripherals_list.DUTMLB.set_pump_duty_cycle(pump_bay = self.target_pump, pump_duty_cycle = self.target_pump_duty)
            if UseSubscribe:
                peripherals_list.DUTMLB.clear_incoming_packet_log()
            while (timeit.default_timer() - startTime) <= self.TIMEOUT:
                if UseSubscribe:
                    DataRead = peripherals_list.DUTMLB.read_all_sensor_packets(limit = None, consume = True)
                    for DataPoint in DataRead:
                        PumpCurrent.append(DataPoint.pump_current_mA)
                else:
                    PumpCurrent.append([round(float(peripherals_list.DUTMLB.get_currents().pump_current_mA), 3)])
                if peripherals_list.gpioSuite.vacSwitchPin1.get() == 0 and peripherals_list.DUTsprinkler.pump1Pass is False:
                    if UseSubscribe:
                        ReturnMessage = peripherals_list.DUTMLB.set_sensor_subscribe(subscribe_frequency = peripherals_list.DUTsprinkler.SubscribeOff)
                        peripherals_list.DUTMLB.clear_incoming_packet_log()
                    ReturnMessage = peripherals_list.DUTMLB.set_pump_duty_cycle(pump_bay = self.target_pump, pump_duty_cycle = 0)
                    peripherals_list.DUTsprinkler.pump1Pass = True
                    peripherals_list.DUTsprinkler.Pump1CurrentAve = round(float(np.average(PumpCurrent)), 1)
                    peripherals_list.DUTsprinkler.Pump1CurrentSTD = round(float(np.std(PumpCurrent)), 2)
                    if self.target_pump == 1:
                        return TestPumpResult(test_status = f"±Pump 1  1号泵: {round(timeit.default_timer() - startTime, 3)} sec, {peripherals_list.DUTsprinkler.Pump1CurrentAve} mA, STD {peripherals_list.DUTsprinkler.Pump1CurrentSTD} mA", step_start_time = startTime, pass_criteria = self.PASS_TIME)
                    else:
                        return TestPumpResult(test_status = self.ERRORS.get("Wrong Pump") + f" Expected 应启动蠕动泵号: {self.target_pump}, Triggered 实际启动蠕动泵号: Pump 蠕动泵 1", step_start_time = startTime, pass_criteria = self.PASS_TIME)
                if peripherals_list.gpioSuite.vacSwitchPin2.get() == 0 and peripherals_list.DUTsprinkler.pump2Pass is False:
                    if UseSubscribe:
                        ReturnMessage = peripherals_list.DUTMLB.set_sensor_subscribe(subscribe_frequency = peripherals_list.DUTsprinkler.SubscribeOff)
                        peripherals_list.DUTMLB.clear_incoming_packet_log()
                    ReturnMessage = peripherals_list.DUTMLB.set_pump_duty_cycle(pump_bay = self.target_pump, pump_duty_cycle = 0)
                    peripherals_list.DUTsprinkler.pump2Pass = True
                    peripherals_list.DUTsprinkler.Pump2CurrentAve = round(float(np.average(PumpCurrent)), 1)
                    peripherals_list.DUTsprinkler.Pump2CurrentSTD = round(float(np.std(PumpCurrent)), 2)
                    if self.target_pump == 2:
                        return TestPumpResult(test_status = f"±Pump 2  2号泵: {round(timeit.default_timer() - startTime, 3)} sec, {peripherals_list.DUTsprinkler.Pump2CurrentAve} mA, STD {peripherals_list.DUTsprinkler.Pump2CurrentSTD} mA", step_start_time = startTime, pass_criteria = self.PASS_TIME)
                    else:
                        return TestPumpResult(test_status=self.ERRORS.get("Wrong Pump") + f" Expected 应启动蠕动泵号: {self.target_pump}, Triggered 实际启动蠕动泵号: Pump 蠕动泵 2", step_start_time = startTime, pass_criteria = self.PASS_TIME)
                if peripherals_list.gpioSuite.vacSwitchPin3.get() == 0 and peripherals_list.DUTsprinkler.pump3Pass is False:
                    if UseSubscribe:
                        ReturnMessage = peripherals_list.DUTMLB.set_sensor_subscribe(subscribe_frequency = peripherals_list.DUTsprinkler.SubscribeOff)
                        peripherals_list.DUTMLB.clear_incoming_packet_log()
                    ReturnMessage = peripherals_list.DUTMLB.set_pump_duty_cycle(pump_bay = self.target_pump, pump_duty_cycle = 0)
                    peripherals_list.DUTsprinkler.pump3Pass = True
                    peripherals_list.DUTsprinkler.Pump3CurrentAve = round(float(np.average(PumpCurrent)), 1)
                    peripherals_list.DUTsprinkler.Pump3CurrentSTD = round(float(np.std(PumpCurrent)), 2)
                    if self.target_pump == 3:
                        return TestPumpResult(test_status = f"±Pump 3  3号泵: {round(timeit.default_timer() - startTime, 3)} sec, {peripherals_list.DUTsprinkler.Pump3CurrentAve} mA, STD {peripherals_list.DUTsprinkler.Pump3CurrentSTD} mA", step_start_time = startTime, pass_criteria = self.PASS_TIME)
                    else:
                        return TestPumpResult(test_status = self.ERRORS.get("Wrong Pump") + f" Expected 应启动蠕动泵号: {self.target_pump}, Triggered 实际启动蠕动泵号: Pump 蠕动泵 3", step_start_time = startTime, pass_criteria = self.PASS_TIME)

            if UseSubscribe:
                ReturnMessage = peripherals_list.DUTMLB.set_sensor_subscribe(subscribe_frequency = peripherals_list.DUTsprinkler.SubscribeOff)
                peripherals_list.DUTMLB.clear_incoming_packet_log()
            ReturnMessage = peripherals_list.DUTMLB.set_pump_duty_cycle(pump_bay = self.target_pump, pump_duty_cycle = 0)
                
            if self.target_pump == 1:
                peripherals_list.DUTsprinkler.Pump1CurrentAve = round(float(np.average(PumpCurrent)), 1)
                peripherals_list.DUTsprinkler.Pump1CurrentSTD = round(float(np.std(PumpCurrent)), 2)
            elif self.target_pump == 2:
                peripherals_list.DUTsprinkler.Pump2CurrentAve = round(float(np.average(PumpCurrent)), 1)
                peripherals_list.DUTsprinkler.Pump2CurrentSTD = round(float(np.std(PumpCurrent)), 2)
            elif self.target_pump == 3:
                peripherals_list.DUTsprinkler.Pump3CurrentAve = round(float(np.average(PumpCurrent)), 1)
                peripherals_list.DUTsprinkler.Pump3CurrentSTD = round(float(np.std(PumpCurrent)), 2)

            if "-v3" not in peripherals_list.DUTsprinkler.Firmware:
                if round(float(np.average(PumpCurrent)), 1) == 0:
                    return TestPumpResult(test_status = f"Pump {self.target_pump} did not run. 蠕动泵号:{self.target_pump} 未启动。\nPump current 蠕动泵内部电流: {round(float(np.average(PumpCurrent)), 1)} mA, STD {round(float(np.std(PumpCurrent)), 2)}", step_start_time = startTime, pass_criteria = self.PASS_TIME)
                elif round(float(np.average(PumpCurrent)), 1) > 600:
                    return TestPumpResult(test_status = f"Pump {self.target_pump} is stalled. 蠕动泵号:{self.target_pump} 堵转。\nPump current: {round(float(np.average(PumpCurrent)), 1)} mA, STD {round(float(np.std(PumpCurrent)), 2)}", step_start_time = startTime, pass_criteria = self.PASS_TIME)
            return TestPumpResult(test_status = self.ERRORS.get("No Pumps") + f" Check {self.CAPS[self.target_pump - 1]} cap is tight. 检查{self.CAPSC[self.target_pump - 1]}色盖子是否拧紧。\nPump current 蠕动泵电流: {round(float(np.average(PumpCurrent)), 1)} mA, STD {round(float(np.std(PumpCurrent)), 2)}", step_start_time = startTime, pass_criteria = self.PASS_TIME)
        else:
            return TestPumpResult(test_status = self.ERRORS.get("Invalid Target Pump"), step_start_time = startTime, pass_criteria = self.PASS_TIME)

class TestPumpResult(TestResult):
    def __init__(self, pass_criteria: float, test_status, step_start_time):
        super().__init__(test_status, step_start_time)
        self.pass_criteria = pass_criteria

class TestSolar(TestStep):
    PASS_VOLTAGE: float = 6.417  # Jan 2023 update ±4σ
    MAX_VOLTAGE: float = 9  # Temporary increase for new LED board
    PASS_CURRENT: float = 40  # update per 141 unit build at Meco Dec 2023
    MAX_CURRENT: float = 345  # update per 141 unit build at Meco Dec 2023
    SI_UNITS: str = "ADC"
    ERRORS: Dict[str,str] = {"Solar Below": 'Solar panel voltage BELOW limit.',
                             "Solar Above": 'Solar panel voltage ABOVE limit.',
                             "No Voltage": 'No solar panel voltage was read from the OtO.',
                             "Solar BelowC": 'Solar panel current BELOW limit.  太阳能板电流低于极限值',
                             "Solar AboveC": 'Solar panel current ABOVE limit.  太阳能板电流高于极限值',
                             "No Current": 'No solar panel current was read from the OtO.\n从洒水器未读取到太阳能板产生电流'
                             }

    def run_step(self, peripherals_list: TestPeripherals):
        startTime = timeit.default_timer()
        if not hasattr(peripherals_list, "gpioSuite"):
            new_gpio = GpioSuite()
            peripherals_list.add_device(new_object = new_gpio)
        peripherals_list.gpioSuite.ledPanelPin.set(0)  #turn on LED
        time.sleep(0.3)
        solarCurrent = round(float(peripherals_list.DUTMLB.get_currents().charge_current_mA), 0)
        peripherals_list.DUTsprinkler.solarCurrent = solarCurrent
        peripherals_list.gpioSuite.ledPanelPin.set(1)  #turn off LED 
        if self.PASS_CURRENT <= solarCurrent <= self.MAX_CURRENT:
            return TestSolarResult(test_status = f"±Solar Panel {solarCurrent}mA", step_start_time = startTime, pass_criteria = self.PASS_CURRENT, actual_current = solarCurrent, actual_voltage = 0)
        elif solarCurrent >= self.MAX_CURRENT:
            return TestSolarResult(test_status = self.ERRORS.get("Solar AboveC") + f"{solarCurrent}mA", step_start_time = startTime, pass_criteria = self.PASS_CURRENT, actual_current = solarCurrent, actual_voltage = 0)
        elif solarCurrent < self.PASS_CURRENT and solarCurrent != 0:
            return TestSolarResult(test_status = self.ERRORS.get("Solar BelowC")+ f"{solarCurrent}mA", step_start_time = startTime, pass_criteria = self.PASS_CURRENT, actual_current = solarCurrent, actual_voltage = 0)
        elif solarCurrent == 0:
            return TestSolarResult(test_status = self.ERRORS.get("No Current"), step_start_time = startTime, pass_criteria = self.PASS_CURRENT, actual_current = solarCurrent, actual_voltage = 0)

class TestSolarResult(TestResult):
    def __init__(self, pass_criteria: float, actual_voltage: float, actual_current: float, test_status, step_start_time):
        super().__init__(test_status, step_start_time)
        self.pass_criteria = pass_criteria
        self.actual_voltage = actual_voltage
        self.actual_current = actual_current

class ValveCalibration(TestStep):

    ERRORS: dict = {"EmptyList": "No valve rotation values were received from OtO.",
                    "BackwardRotation": "Valve rotating backwards!"}
    VALVE_ROTATION_DUTY_CYCLE = 90
    TurnRecordingOn = 1875000  # Turn recording on when ADC pressure value is below this value.
    MaxAngleBeforeShutoff = 12000  # how far to rotate before pressure must have dropped below TurnRecordingOn value
    MaxPeakDifference = 91000  # maximum ADC pressure difference between the two peaks per 2411 data
    MaxAngleDifference = 400  # maximum allowable difference in angle (centideg) between peaks from 180°
    TIMEOUT = 20
    MAXVMotorCurrent = 240  # values in mA from first 2,000 piece Meco builds Jan 2024
    MINVMotorCurrent = 60  # 2410/2411 data
    MAXVMotorCurrentSTD = 20
    MINVMotorCurrentSTD = 0.2  # 2410/2411 data

    def __init__(self, name: str, parent: tk, reset: bool):
        super().__init__(name, parent)
        self.reset = reset

    def run_step(self, peripherals_list: TestPeripherals):
        start_time = timeit.default_timer()

        CurrentValvePosition = 0
        data_count = 0
        Info = []
        Info_DF = None
        first_peak = 0
        fullyOPEN_valve_position = 0       
        main2peaks_position = [None, None]
        peak_position_list = []
        peak_pressure_list = []
        PressureData = []
        PreviousValvePosition = 0
        read_all_sensor_outputs = []
        SamplingFrequency = 100
        second_peak = 0
        sensor_read_list = []
        valve_calibration_data = []
        valve_offset = 0
        ValveCurrent = []
        ValvePositionData = []
        TotalTravel = 0

        peripherals_list.DUTMLB.use_moving_average_filter(True)
        CurrentValvePosition = int(peripherals_list.DUTMLB.get_sensors().valve_position_centideg)
        
        # Rotate valve backwards 5 degrees to make sure it can!
        TestPosition = (CurrentValvePosition + 35500) % 36000
        ReturnMessage = peripherals_list.DUTMLB.set_valve_position(valve_position_centideg = TestPosition, wait_for_complete = True)
        if ReturnMessage.message_type_string != "CTRL_OUT_COMMAND_COMPLETE":
            return ValveCalibrationResult (test_status = "Valve won't rotate backwards!  球阀无法反转", step_start_time = start_time)
        if not hasattr(peripherals_list, "gpioSuite"): # if called by itself by one button press
            new_gpio = GpioSuite()
            peripherals_list.add_device(new_object = new_gpio)
        sensor_read_list.clear()  # make sure list is empty
        ValveCurrent.clear()
        RotationComplete = False
        TotalTravel = 0
        CurrentValvePosition = int(peripherals_list.DUTMLB.get_sensors().valve_position_centideg)
        peripherals_list.gpioSuite.airSolenoidPin.set(0) # turn on air 
        # start valve motor turning at desired duty cycle
        peripherals_list.DUTMLB.set_valve_duty(duty_cycle = self.VALVE_ROTATION_DUTY_CYCLE, direction = 1)
        # turn on OtO data acquisition at 100Hz
        peripherals_list.DUTMLB.set_sensor_subscribe(subscribe_frequency = peripherals_list.DUTsprinkler.SubscribeFrequency)
        time.sleep(0.1) # to ignore first few filtered pressure values
        peripherals_list.DUTMLB.clear_incoming_packet_log()

        Recording = False
        FlipFirst = False

        while (timeit.default_timer() - start_time) <= self.TIMEOUT and not RotationComplete:
            ValveCurrent.extend([round(float(peripherals_list.DUTMLB.get_currents().valve_current_mA), 3)])
            read_all_sensor_outputs = peripherals_list.DUTMLB.read_all_sensor_packets(limit = None, consume = True)
            for ReadPoint in read_all_sensor_outputs:
                PreviousValvePosition = CurrentValvePosition
                CurrentValvePosition = int(ReadPoint.valve_position_centideg)
                if Recording:
                    sensor_read_list.append(ReadPoint)
                    if CurrentValvePosition < PreviousValvePosition:  # either rotating backwards or passed 360°
                        if np.sin(np.pi*PreviousValvePosition/18000) < 0:  # sine should be negative in previous position if passing 360°
                            FlipFirst = False
                        else:  # if sine is positive and previous is greater than current position, the valve is turning backward so shut down data collection and rotation on the OtO, then error out.
                            peripherals_list.gpioSuite.airSolenoidPin.set(1)  #turn off air
                            peripherals_list.DUTMLB.set_sensor_subscribe(subscribe_frequency = peripherals_list.DUTsprinkler.SubscribeOff)
                            peripherals_list.DUTMLB.clear_incoming_packet_log()
                            peripherals_list.DUTMLB.set_valve_duty(duty_cycle = 0, direction = 0)
                            return ValveCalibrationResult(test_status = self.ERRORS.get("BackwardRotation"), step_start_time = start_time)
                    else:
                        if not FlipFirst and CurrentValvePosition >= StartPosition:
                            RotationComplete = True
                            break
                else:
                    if int(ReadPoint.pressure_adc) <= self.TurnRecordingOn:
                        Recording = True
                        StartPosition = CurrentValvePosition
                        FlipFirst = True
                    else:
                        if CurrentValvePosition < PreviousValvePosition:  # either rotating backwards or passed 360°
                            if np.sin(np.pi*PreviousValvePosition/18000) < 0:  # sine should be negative in previous position if passing 360°
                                TotalTravel = TotalTravel + CurrentValvePosition + 36000 - PreviousValvePosition
                            else:  # if sine is positive and previous is greater than current position, the valve is turning backward so shut down data collection and rotation on the OtO, then error out.
                                peripherals_list.gpioSuite.airSolenoidPin.set(1)  #turn off air
                                peripherals_list.DUTMLB.set_sensor_subscribe(subscribe_frequency = peripherals_list.DUTsprinkler.SubscribeOff)
                                peripherals_list.DUTMLB.clear_incoming_packet_log()
                                peripherals_list.DUTMLB.set_valve_duty(duty_cycle = 0, direction = 0)
                                return ValveCalibrationResult(test_status = self.ERRORS.get("BackwardRotation"), step_start_time = start_time)
                        else:
                            TotalTravel = TotalTravel + CurrentValvePosition - PreviousValvePosition
                        if TotalTravel >= self.MaxAngleBeforeShutoff:
                            RotationComplete = True

        peripherals_list.gpioSuite.airSolenoidPin.set(1)  #turn off air
        # turn off OtO data acquisition
        peripherals_list.DUTMLB.set_sensor_subscribe(subscribe_frequency = peripherals_list.DUTsprinkler.SubscribeOff)
        peripherals_list.DUTMLB.clear_incoming_packet_log()
        # turn off valve rotation
        ReturnMessage = peripherals_list.DUTMLB.set_valve_duty(duty_cycle = 0, direction = 0)

        peripherals_list.DUTsprinkler.ValveCurrentAve = round(float(np.average(ValveCurrent)), 1)
        peripherals_list.DUTsprinkler.ValveCurrentSTD = round(float(np.std(ValveCurrent)), 2)

        valve_calibration_data.clear()  # make sure the list is empty
        for sensor_message in sensor_read_list:
            Pressure = int(sensor_message.pressure_adc)
            Position = int(sensor_message.valve_position_centideg)
            valve_calibration_data.append([Position, Pressure])
            data_count += 1

        Date_Time = str(datetime.now().strftime("%d-%m-%Y %H_%M_%S"))
        UnitName = peripherals_list.DUTsprinkler.deviceID
        bom_Number = peripherals_list.DUTsprinkler.bomNumber
        Info = ([f"Unit Name: {UnitName}", f"Test Time: {Date_Time}" , f"BOM Number: {bom_Number}"])
        Info_DF = pd.DataFrame(Info)
        
        if not valve_calibration_data: 
            return ValveCalibrationResult (test_status = self.ERRORS.get("EmptyList"), step_start_time = start_time)

        if UnitName != "":
            file_path = EstablishLoggingLocation(name = "CollectRawDataWithSubscribe", folder_name = "Valve Calibrate", date_time = Date_Time, parent = self.parent).run_step(peripherals_list=peripherals_list).file_path
            data = pd.DataFrame(valve_calibration_data)
            data = data.merge(Info_DF, suffixes=['_left', '_right'], left_index = True, right_index = True, how = 'outer')
            data.columns = ["Position" , "Pressure" , "Unit Info"]
            data.to_csv(file_path, encoding='utf-8')
        
        peripherals_list.DUTsprinkler.valveRawData = valve_calibration_data

        self.parent.text_console_logger(f"Valve Motor {peripherals_list.DUTsprinkler.ValveCurrentAve} mA, STD {peripherals_list.DUTsprinkler.ValveCurrentSTD} mA")

        pressure_sensor_check = peripherals_list.DUTMLB.get_pressure_sensor_version().pressure_sensor_version
        if socket.gethostname() not in KK_LAPTOP_LIST:
            if pressure_sensor_check == peripherals_list.DUTsprinkler.psig15:
                minimum_acceptable_peak_pressure = 4000000 # ADC, about 1 psi
                maximum_acceptable_peak_pressure = 6000000 # ADC, about 4.8 psi
                self.MaxPeakDifference = 150000  # maximum pressure difference between the two peaks
                self.MaxAngleDifference = 210  # maximum allowable difference in angle (centideg) between peaks from 180°
            elif pressure_sensor_check == peripherals_list.DUTsprinkler.psig30:
                minimum_acceptable_peak_pressure = 2680000  # Apr 2023 match FOT values
                maximum_acceptable_peak_pressure = 3790000  # Apr 2023 match FOT values
            else:
                return ValveCalibrationResult (test_status = "Can't identify pressure sensor!", step_start_time = start_time)
        else:
            if pressure_sensor_check == peripherals_list.DUTsprinkler.psig15:
                minimum_acceptable_peak_pressure = 3500000 # LEAVING ALONE TO MATCH PRODUCTION
                maximum_acceptable_peak_pressure = 6000000 # 2022/09/04 UPDATE 4 STD
                self.MaxPeakDifference = 150000  # maximum pressure difference between the two peaks
                self.MaxAngleDifference = 210  # maximum allowable difference in angle (centideg) between peaks from 180°
            elif pressure_sensor_check == peripherals_list.DUTsprinkler.psig30:
                minimum_acceptable_peak_pressure = 2680000  # LEAVING ALONE TO MATCH PRODUCTION
                maximum_acceptable_peak_pressure = 6315845  # 2022/09/04 UPDATE 3 STD
            else:
                return ValveCalibrationResult (test_status = "Can't identify pressure sensor!", step_start_time = start_time)

        ValvePositionData.clear()
        PressureData.clear()
        for i in range(len(valve_calibration_data)):
            ValvePositionData.append(valve_calibration_data[i][0])
            PressureData.append(valve_calibration_data[i][1])
        
        self.parent.create_plot(window = self.parent.GraphHolder, plottype = "lineplot", xaxis = ValvePositionData, yaxis = PressureData, size = 12, name = "Valve Calibration 校准阀门", clear = False)

        sos = signal.butter(N = 2, Wn = 0.6, btype = "lowpass", output = "sos", fs = SamplingFrequency)
        FinalPressure = signal.sosfiltfilt(sos, x = PressureData, padtype = "odd", padlen = 50)
        
        self.parent.create_plot(window = self.parent.GraphHolder, plottype = "lineplot", xaxis = ValvePositionData, yaxis = FinalPressure, size = 15, name = "Valve Calibration 校准阀门", clear = False)

        peak_list_index, properties = find_peaks(FinalPressure)
        
        peak_position_list.clear()
        peak_pressure_list.clear()
        for i in range(len(peak_list_index)):
            peak_position_list.append(ValvePositionData[peak_list_index[i]])
            peak_pressure_list.append(FinalPressure[peak_list_index[i]])

        try:
            first_peak = max(peak_pressure_list)
        except:
            first_peak = 0

        for i in range(len(peak_list_index)):
            if peak_pressure_list[i] != first_peak:
                if peak_pressure_list[i] > second_peak:
                    second_peak = peak_pressure_list[i]
        
        main2peaks_position = [None, None]
        for i in range(len(peak_list_index)):
            if first_peak == peak_pressure_list[i]:
                main2peaks_position[0] = peak_position_list[i]
            if second_peak == peak_pressure_list[i]:
                main2peaks_position[1] = peak_position_list[i]

        if main2peaks_position[0] != None and main2peaks_position[1] != None:
            fullyOPEN_valve_position = main2peaks_position[0]  # main2peaks_position[0]  # Pass 0 or 1 for either closed valve position
            valve_offset = (fullyOPEN_valve_position + 27000) % 36000  # closed position is minus 90° from fully open.
            peripherals_list.DUTsprinkler.valveOffset = int(valve_offset)
            peripherals_list.DUTsprinkler.valveFullyOpen = int(fullyOPEN_valve_position)
            self.parent.text_console_logger(f"Relative Valve Closed: {valve_offset/100}°, Open: {fullyOPEN_valve_position/100}°")
            self.parent.create_plot(window = self.parent.GraphHolder, plottype = "lineplot", xaxis = [fullyOPEN_valve_position], yaxis = [first_peak], size = 80, name = "Valve Calibration 校准阀门", clear = False)
            self.parent.create_plot(window = self.parent.GraphHolder, plottype = "lineplot", xaxis = [main2peaks_position[1]], yaxis = [second_peak], size = 60, name = "Valve Calibration 校准阀门", clear = True)
            if first_peak != 0:
                if abs(first_peak - peripherals_list.DUTsprinkler.ZeroPressureAve) < 150000:
                    return ValveCalibrationResult (test_status = "Possible plugged or disconnected pressure sensor!  压力传感器可能被堵住", step_start_time = start_time)
                elif first_peak <= minimum_acceptable_peak_pressure:
                    return ValveCalibrationResult (test_status = f"Pressure reading is too low!  {first_peak:,.0f} ADC  压力值太低", step_start_time = start_time)
                elif first_peak >= maximum_acceptable_peak_pressure:
                    return ValveCalibrationResult (test_status = f"Pressure reading is too high! {first_peak:,.0f} ADC  压力值太高", step_start_time = start_time)
                elif first_peak - second_peak > self.MaxPeakDifference:
                    return ValveCalibrationResult (test_status = f"First and second peak pressures are too different! {(first_peak - second_peak):,.0f} ADC  压力值太高", step_start_time = start_time)
                PositionDifference = abs(abs(main2peaks_position[0] - main2peaks_position[1]) - 18000)
                if PositionDifference > self.MaxAngleDifference:
                    return ValveCalibrationResult (test_status = f"First and second peak angles are not 180°±{self.MaxAngleDifference/100} apart! {abs(main2peaks_position[0] - main2peaks_position[1])/100:.1f}  压力值太高", step_start_time = start_time)
        else:
            return ValveCalibrationResult (test_status = "No peaks found in data!  无法找到峰值", step_start_time = start_time)
        
        if "-v3" not in peripherals_list.DUTsprinkler.Firmware:
            if peripherals_list.DUTsprinkler.ValveCurrentAve > self.MAXVMotorCurrent or peripherals_list.DUTsprinkler.ValveCurrentAve < self.MINVMotorCurrent:
                return ValveCalibrationResult (test_status = f"Valve motor current is not in range! {self.MINVMotorCurrent}-{self.MAXVMotorCurrent}mA\n阀门电机电流不在范围内!", step_start_time = start_time)            
            if peripherals_list.DUTsprinkler.ValveCurrentSTD > self.MAXVMotorCurrentSTD or peripherals_list.DUTsprinkler.ValveCurrentSTD < self.MINVMotorCurrentSTD:
                return ValveCalibrationResult (test_status = f"Valve motor current variation too large! {self.MINVMotorCurrentSTD}-{self.MAXVMotorCurrentSTD}mA\n阀门电机电流变化过大!", step_start_time = start_time)            

        try:
            saved_MLB = int(peripherals_list.DUTMLB.get_valve_home_centidegrees().number) #this is abs
        except peripherals_list.DUTsprinkler.NoNVSException:
            saved_MLB = 0
        except Exception as e:
            return ValveCalibrationResult (test_status = str(e), step_start_time = start_time)
        calculated_offset = peripherals_list.DUTsprinkler.valveOffset # this is relative
        valve_Offset = (saved_MLB + calculated_offset + 35900) % 36000 # this makes it absolute, adjust for lag by -1°
        absolute_fully_open = (int(valve_Offset) + 9000) % 36000
        Peak1Angle = (int(saved_MLB + main2peaks_position[0]) % 36000)/100
        Peak2Angle = (int(saved_MLB + main2peaks_position[1]) % 36000)/100
        ValvePeak1 = int(first_peak)
        ValvePeak2 = int(second_peak)
        self.parent.text_console_logger(f"Absolute Peak 1: {Peak1Angle}°, {ValvePeak1:,} ADC, Peak 2: {Peak2Angle}°, {ValvePeak2:,} ADC")
        if self.reset:
            peripherals_list.DUTMLB.set_valve_home_centidegrees(int(valve_Offset)) # we write the absolute value back to the MLB
            peripherals_list.DUTsprinkler.valveOffset = int(valve_Offset)
            peripherals_list.DUTsprinkler.valveFullyOpen = int(absolute_fully_open)
            peripherals_list.DUTsprinkler.Peak1Angle = Peak1Angle
            peripherals_list.DUTsprinkler.Peak2Angle = Peak2Angle
            peripherals_list.DUTsprinkler.ValvePeak1 = ValvePeak1
            peripherals_list.DUTsprinkler.ValvePeak2 = ValvePeak2
            self.parent.text_console_logger(f"Absolute Valve Closed: {valve_Offset/100}°, Open: {absolute_fully_open/100}°")
            fw_ValveOffset = int(peripherals_list.DUTMLB.get_valve_home_centidegrees().number)
            memory_ValveOffset = peripherals_list.DUTsprinkler.valveOffset
            if fw_ValveOffset != memory_ValveOffset:
                return ValveCalibrationResult (test_status = f"OtO's saved valve position {fw_ValveOffset/100}° does not match computer value {memory_ValveOffset/100}°.", step_start_time = start_time)
        else:
            self.parent.text_console_logger(f"Absolute difference: {(valve_Offset - saved_MLB)/100}°")
        return ValveCalibrationResult (test_status = None, step_start_time = start_time)

class ValveCalibrationResult(TestResult):
    def __init__(self, test_status: Union[str, None], step_start_time: float):
        super().__init__(test_status, step_start_time)

class VerifyValveOffsetTarget(TestStep): 

    ERROR: Dict[str,str] = {"Pressure_Sensor": "OtO's pressure sensor isn't recognized.  洒水器的压力传感器无法识别",
                        "NonZeroPressure": "OtO's valve is leaking when closed.  洒水器阀门关闭时仍漏气",
                        "NotFullyClosed": "Unable to close OtO's valve.  无法关闭洒水器阀门",
                        "Empty List": "OtO did not return pressure information.  洒水器未反馈压力数据",
                        "Timeout": "Valve didn't reach target in time.  阀门无法及时转到目标位置"}
    VALVE_TARGET_TOLERANCE: int = 25  # in centidegree
    Zero_P_Collection_time = 3
    REPEAT_TEST = 1

    # Use "Hard Coded" or "Test Calibration" for fixed characters or using the calibration test outputs respectively! 
    def __init__(self, name: str, parent: tk, method:str = "Test Calibration"):
        super().__init__(name, parent)
        self.Zero_Pressure_Calibration_Method = method

    def run_step(self, peripherals_list: TestPeripherals):  
        startTime = timeit.default_timer()
        pressure_sensor_check = int(peripherals_list.DUTMLB.get_pressure_sensor_version().pressure_sensor_version)
        if socket.gethostname() not in KK_LAPTOP_LIST:
            pressure_sensor_check = peripherals_list.DUTMLB.get_pressure_sensor_version().pressure_sensor_version
            if pressure_sensor_check == peripherals_list.DUTsprinkler.psig15:
                self.PRESSURE_ADC_TOLERANCE = 530  # ± this amount, based on 800 pcs data Jan 2023
                self.STD_LOWER_LIMIT_TO_MEAN = 107.8  # based on 800 pcs data Jan 2023
                self.STD_UPPER_LIMIT_TO_MEAN = 104.2
            elif pressure_sensor_check == peripherals_list.DUTsprinkler.psig30:
                self.PRESSURE_ADC_TOLERANCE = 325  # ± this amount, based on 1,089 pcs data Jan 2024
                self.STD_LOWER_LIMIT_TO_MEAN = 50  # based on 44 pcs data Jan 2023, loose limit for update after a few days of production.
                self.STD_UPPER_LIMIT_TO_MEAN = 50
            else:
                return VerifyValveOffsetTargetResult(test_status=self.ERRORS.get("Pressure_Sensor"),step_start_time=startTime, Valve_Target=False,pressureReading=None,Relative_valveOffset=0, Actual_Valve_Position=0)
        else: # unit is at the RMA location
            if pressure_sensor_check == peripherals_list.DUTsprinkler.psig15:
                self.PRESSURE_ADC_TOLERANCE = 65940 # 2023/09/04 3 STD AT KK
                self.STD_LOWER_LIMIT_TO_MEAN = 308 # 2023/09/04 3 STD AT KK
                self.STD_UPPER_LIMIT_TO_MEAN = 308 # 2023/09/04 3 STD AT KK
            elif pressure_sensor_check == peripherals_list.DUTsprinkler.psig30:
                self.PRESSURE_ADC_TOLERANCE = 60562 # 2023/09/04 3 STD AT KK
                self.STD_LOWER_LIMIT_TO_MEAN = 464 # 2023/09/04 3 STD AT KK
                self.STD_UPPER_LIMIT_TO_MEAN = 464 # 2023/09/04 3 STD AT KK
            else:
                return VerifyValveOffsetTargetResult(test_status=self.ERRORS.get("Pressure_Sensor"),step_start_time=startTime, Valve_Target=False,pressureReading=None,Relative_valveOffset=0, Actual_Valve_Position=0)

        if not hasattr(peripherals_list, "gpioSuite"): # if called by itself by one button press
            new_gpio = GpioSuite()
            peripherals_list.add_device(new_object = new_gpio)
        valveTarget = 0 # Relative position for fully closed
        valve_position = None
        pressure_reading = None
        sensor_read_list: list = []
        pressure_data_list:list = []
        pressure_data: list = []
        data_reading_loop_startTime = None
        UnitName = None
        dataCount = 0
        run_counter = 0

        if self.Zero_Pressure_Calibration_Method == "Hard Coded":
            zero_P_ADC = 1702005
            zeroTolerance = 3000
        else:
            if not(peripherals_list.DUTsprinkler.ZeroPressure):
                zero_P_ADC = 1680000
                zeroTolerance = 5000
            else:
                zero_P_ADC = peripherals_list.DUTsprinkler.ZeroPressure[0]
                zeroTolerance = peripherals_list.DUTsprinkler.ZeroPressure[1]
                multiple_STD = peripherals_list.DUTsprinkler.ZeroPressure[2]

        peripherals_list.DUTMLB.use_moving_average_filter(True)
        while run_counter < self.REPEAT_TEST:
            run_counter += 1

            if run_counter == 2:
                valveTarget = 18000

            try: # Closing the valve
                ReturnMessage = peripherals_list.DUTMLB.set_valve_position(valve_position_centideg = valveTarget, wait_for_complete = True)
            except TimeoutError:
                return VerifyValveOffsetTargetResult(test_status=self.ERRORS.get("Timeout"), step_start_time=startTime, Valve_Target=False, pressureReading=pressure_reading, Relative_valveOffset=valveTarget, Actual_Valve_Position=valve_position)
            except Exception as e:
                return VerifyValveOffsetTargetResult(test_status=str(e), step_start_time=startTime, Valve_Target=False, pressureReading=pressure_reading, Relative_valveOffset=valveTarget, Actual_Valve_Position=valve_position)

            sensor_reading = peripherals_list.DUTMLB.get_sensors()
            valve_position = int(sensor_reading.valve_position_centideg)

            if ReturnMessage.message_type_string != "CTRL_OUT_COMMAND_COMPLETE":
                return VerifyValveOffsetTargetResult(test_status=self.ERRORS.get("Timeout"), step_start_time=startTime, Valve_Target=False, pressureReading=pressure_reading, Relative_valveOffset=valveTarget, Actual_Valve_Position=valve_position)
            else:
                peripherals_list.gpioSuite.airSolenoidPin.set(0) # turn on air
            
            peripherals_list.DUTMLB.set_sensor_subscribe(subscribe_frequency = peripherals_list.DUTsprinkler.SubscribeFrequency)
            time.sleep(0.3)
            peripherals_list.DUTMLB.clear_incoming_packet_log()
            data_reading_loop_startTime = time.perf_counter()
            while time.perf_counter() - data_reading_loop_startTime <= self.Zero_P_Collection_time:
                sensor_read_list.extend(peripherals_list.DUTMLB.read_all_sensor_packets(limit = None, consume = True))
            peripherals_list.gpioSuite.airSolenoidPin.set(1) # turn off air
            peripherals_list.DUTMLB.set_sensor_subscribe(subscribe_frequency = peripherals_list.DUTsprinkler.SubscribeOff)
            peripherals_list.DUTMLB.clear_incoming_packet_log()

            if not sensor_read_list:
                return VerifyValveOffsetTargetResult(test_status = self.ERRORS.get("Empty List"), step_start_time = startTime, Valve_Target = False, pressureReading = pressure_reading, Relative_valveOffset=valveTarget,Actual_Valve_Position=valve_position)
            
            for dataCount, dataset in enumerate(sensor_read_list):
                pressure_data_list.append([int(dataset.time_ms) , int(dataset.pressure_adc)])
                pressure_data.append(int(dataset.pressure_adc))

            pressure_reading = round(float(np.mean(pressure_data)), 0)
            STD_pressure_reading = round(float(np.std(pressure_data)), 1)
            peripherals_list.DUTsprinkler.valveClosesAve = pressure_reading
            peripherals_list.DUTsprinkler.valveClosesSTD = STD_pressure_reading

            UnitName = peripherals_list.DUTsprinkler.deviceID
            bom_Number = peripherals_list.DUTsprinkler.bomNumber
            setting_n_output = ([f"Checking closed pressure", f"Unit ID: {UnitName}", f"Trial: {run_counter}",f"Mean: {pressure_reading}", 
                                f"STD: {STD_pressure_reading}", f"Data points: {dataCount+1}" , f"BOM: {bom_Number}"])

            setting_n_output = pd.DataFrame(setting_n_output)
            Data = pd.DataFrame(pressure_data_list)
            Data = Data.merge(setting_n_output, suffixes=['_left', '_right'], left_index = True, right_index = True, how = 'outer')
            Data.columns = ["Timestamp" , "Pressure Reading" , "More info"]
            Date_Time = str(datetime.now().strftime("%d-%m-%Y %H_%M_%S"))

            self.parent.create_plot(window = self.parent.GraphHolder, plottype = "histplot", xaxis = pressure_data, yaxis = None, size = None, name = "Closed Valve Zero 验证阀门关闭", clear = False)

            if UnitName != "":
                file_name = EstablishLoggingLocation(name = "Verify valve position", folder_name = "Closed", date_time = Date_Time, parent = self.parent).run_step(peripherals_list=peripherals_list).file_path
                Data.to_csv(file_name, encoding = "utf-8")

            if valve_position > 18000:
                valve_position = abs(36000 - valve_position)
            if valve_position <= (valveTarget + self.VALVE_TARGET_TOLERANCE):
                if (pressure_reading <= zero_P_ADC + self.PRESSURE_ADC_TOLERANCE) and (pressure_reading >= zero_P_ADC - self.PRESSURE_ADC_TOLERANCE) and \
                    (STD_pressure_reading <= zeroTolerance/multiple_STD + self.STD_UPPER_LIMIT_TO_MEAN) and \
                    (STD_pressure_reading >= zeroTolerance/multiple_STD - self.STD_LOWER_LIMIT_TO_MEAN):
                    if run_counter == 2:
                        peripherals_list.DUTsprinkler.valveOffset = valveTarget
                        saved_MLB = int(peripherals_list.DUTMLB.get_valve_home_centidegrees().number) #this is abs
                        valve_Offset = (saved_MLB + valveTarget) % 36000 # this makes it absolute
                        absolute_fully_open = (int(valve_Offset) + 9000) % 36000
                        peripherals_list.DUTMLB.set_valve_home_centidegrees(int(valve_Offset)) # we write the absolute value back to the MLB
                        peripherals_list.DUTsprinkler.valveOffset = int(valve_Offset)
                        peripherals_list.DUTsprinkler.valveFullyOpen = int(absolute_fully_open)
                        self.parent.text_console_logger(f"Absolute Valve Closed: {valve_Offset/100}°, Open: {absolute_fully_open/100}°")
                        fw_ValveOffset = int(peripherals_list.DUTMLB.get_valve_home_centidegrees().number)
                        memory_ValveOffset = peripherals_list.DUTsprinkler.valveOffset
                        if fw_ValveOffset != memory_ValveOffset:
                            return VerifyValveOffsetTargetResult(test_status = f"OtO's saved valve position {fw_ValveOffset/100}° does not match computer value {memory_ValveOffset/100}°.\n洒水器保存的喷嘴位置与电脑规定值不符", step_start_time = startTime, Valve_Target=True,
                                                        pressureReading=pressure_reading,
                                                        Relative_valveOffset=valveTarget,
                                                        Actual_Valve_Position=valve_position)
                    return VerifyValveOffsetTargetResult(test_status = f"±Closed Valve Pressure  关闭的阀门的压力: {pressure_reading:,} ADC, STD {STD_pressure_reading:,}", step_start_time=startTime, Valve_Target=True,
                                                        pressureReading=pressure_reading,
                                                        Relative_valveOffset=valveTarget,
                                                        Actual_Valve_Position=valve_position)
                else:
                    if run_counter >= self.REPEAT_TEST:
                        return VerifyValveOffsetTargetResult(test_status=self.ERROR.get("NonZeroPressure") + f"\nPressure: {pressure_reading:,} ADC, STD {STD_pressure_reading:,} Valve Error: {round((valveTarget - valve_position)/100, 2)}°", step_start_time=startTime, Valve_Target=False, pressureReading=pressure_reading, Relative_valveOffset=valveTarget, Actual_Valve_Position=valve_position)
            else:
                if run_counter != 1:
                    return VerifyValveOffsetTargetResult(test_status=self.ERRORS.get("NotFullyClosed") + f"Offset: {valveTarget/100}°±{self.VALVE_TARGET_TOLERANCE/100}° ; Reading {valve_position/100}°", pressureReading = pressure_reading, Relative_valveOffset = valveTarget, Actual_Valve_Position = valve_position)

class VerifyValveOffsetTargetResult(TestResult):

    def __init__(self, test_status: Union[str, None], step_start_time, Valve_Target: bool, pressureReading: int,
                 Relative_valveOffset: int, Actual_Valve_Position: int):

        super().__init__(test_status, step_start_time)
        self.Valve_Target = Valve_Target
        self.pressureReading = pressureReading
        self.Actual_Valve_Position = Actual_Valve_Position
        self.Relative_valveOffset = Relative_valveOffset