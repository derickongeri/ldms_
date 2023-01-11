import enum
from django.utils.translation import gettext as _

class KeyValueBaseEnum(enum.Enum):
	"""Enumeration for items with key and label properties
	"""
	@property
	def key(self):
		return self.value[0]

	@property
	def label(self):
		return self.value[1]

class KeyValueIndexBaseEnum(KeyValueBaseEnum):
	"""Enumeration for items with key, label and index properties
	"""
	@property
	def index(self):
		return self.value[2]

class LCEnum(enum.Enum):
	"""Enumeration for different land covers
	"""
	WATER = 1
	BARELAND = 2
	ARTIFICIAL = 3
	WETLAND = 4
	CROPLAND = 5
	GRASSLAND = 6
	FOREST = 7


class LulcCalcEnum(enum.Enum):
	"""
	Enumeration for different types of LULC computations
	"""
	LULC = 0
	LULC_CHANGE = 1

class ForestChangeEnum(enum.Enum):
	"""
	Enumeration for different types of Forest Change computations
	"""
	FOREST_LOSS = 0
	FOREST_GAIN = 1

class LulcChangeEnum(KeyValueBaseEnum):
	"""
	Enumeration for different types of LULC change
	"""
	DEGRADED = (2, _("Degradation"))
	STABLE = (0, _("Stable"))
	IMPROVED = (1, _("Improvement")) 

class SOCChangeEnum(KeyValueBaseEnum):
	"""
	Enumeration for different types of SOC change
	"""
	STABLE = (0, _("Stable"))
	IMPROVED = (1, _("Potential Improvement"))
	DEGRADED = (2, _("Potential Degradation"))
		
class ClimaticRegionEnum(enum.Enum):
	"""
	Enumeration for the different climatic conditions.
	Manages Land Use coefficients when computing SOC
	"""
	TemperateDry = (1, 0.8)
	TemperateMoist = (2, 0.69)
	TropicalDry = (3, 0.58)
	TropicalMoist = (4, 0.48)
	TropicalMontane = (5, 0.64)

	@property
	def id(self):
		"""
		Return the unique id for SOC computation
		"""
		return self.value[0]
	
	@property
	def coeff(self):
		"""
		Return the coefficient value for SOC computation
		"""
		return self.default_f
		# return self.value[1]
	
	@property
	def default_f(self):
		"""
		Return default f where climatic region is unknown
		"""
		return 0.6


class TrajectoryChangeBinaryEnum(KeyValueBaseEnum):
	"""
	Enumeration for different types of productivity trend/trajectory with 2 values
	"""
	DEGRADED = (0, _("Degraded"))
	NOT_DEGRADED = (1, _("Not Degraded"))

class TrajectoryChangeTernaryEnum(KeyValueBaseEnum):
	"""
	Enumeration for different types of productivity trend/trajectory with 3 values
	"""
	STABLE = (0, _("Stable"))
	IMPROVED = (1, _("Potential Improvement"))
	DEGRADED = (2, _("Potential Degradation"))

class TrajectoryChangeQuinaryEnum(KeyValueBaseEnum):
	"""
	Enumeration for different Productivity Trajectory / Trend change with 5 values
	"""
	DEGRADED = (1, _("Degraded"))
	RISK_OF_DEGRADING = (2, _("At risk of degrading"))
	NO_CHANGE  = (3, _("No significant change"))
	POTENTIALLY_IMPROVING = (4, _("Potentially improving"))
	IMPROVING = (5, _("Improving"))

class StateChangeBinaryEnum(KeyValueBaseEnum):
	"""
	Enumeration for different types of Productivity State change with 2 states
	"""
	DEGRADED = (0, _("Degraded"))
	NOT_DEGRADED = (1, _("Not Degraded"))
	
class StateChangeTernaryEnum(KeyValueBaseEnum):
	"""
	Enumeration for different types of Productivity State change with 3 states
	"""
	STABLE = (0, _("Stable"))
	IMPROVED = (1, _("Potential Improvement"))
	DEGRADED = (2, _("Potential Degradation"))

class StateChangeQuinaryEnum(KeyValueBaseEnum):
	"""
	Enumeration for different Productivity State change with 5 values
	"""
	DEGRADED = (1, _("Degraded"))
	RISK_OF_DEGRADING = (2, _("At risk of degrading"))
	NO_CHANGE  = (3, _("No significant change"))
	POTENTIALLY_IMPROVING = (4, _("Potentially improving"))
	IMPROVING = (5, _("Improving"))

class StateChangeBinaryEnum(KeyValueBaseEnum):
	"""
	Enumeration for different Productivity State to show if degraded and not-degraded
	"""
	DEGRADED = (1, _("Degraded"))
	NOT_DEGRADED = (2, _("Not degraded"))

class PerformanceChangeBinaryEnum(KeyValueBaseEnum):
	"""
	Enumeration for different types of Productivity Performance change
	"""
	STABLE = (0, _("Stable"))
	DEGRADED = (2, _("Potential Degradation"))
	
class ProductivityChangeBinaryEnum(KeyValueBaseEnum):
	"""
	Enumeration for different types of Overall Productivity change with 2 values
	"""
	DEGRADED = (1, _("Degraded"))
	NOT_DEGRADED = (2, _("Not Degraded"))
class ProductivityChangeTernaryEnum(KeyValueBaseEnum):
	"""
	Enumeration for different types of Overall Productivity change with 3 values
	"""
	STABLE = (0, _("Stable"))
	IMPROVED = (1, _("Improvement"))
	DEGRADED = (2, _("Degradation"))
	
class BinaryLandDegradationChangeEnum(KeyValueBaseEnum):
	"""
	Enumeration for binary types of LandDegradation change (Degraded and Not-degraded)
	"""
	IMPROVED = (1, _("Not degraded"))
	DEGRADED = (2, _("Degraded"))
	
class LandDegradationChangeEnum(KeyValueBaseEnum):
	"""
	Enumeration for different types of LandDegradation change
	"""
	STABLE = (0, _("Stable"))
	IMPROVED = (1, _("Not degraded"))
	DEGRADED = (2, _("Degraded"))
class AridityIndexEnum(KeyValueBaseEnum):
	"""
	Enumeration for different types of Aridity Index Change
	"""
	HYPER_ARID = (1, _("Hyper-arid"))
	ARID = (2, _("Arid"))
	SEMI_ARID = (3, _("Semi-arid"))
	DRY_SUBHUMID = (4, _("Dry sub-humid"))
	MOIST_SUBHUMID = (5, _("Moist sub-humid"))
	HUMID = (6, _("Humid"))

class ManagementQualityIndexEnum(KeyValueBaseEnum):
	"""
	Enumeration for different management quality index

	Args:
		enum ([type]): [description]

	Returns:
		[type]: [description]
	"""
	HIGH_QUALITY = (1, _("High"))
	MODERATE_QUALITY = (2, _("Moderate"))
	LOW_QUALITY = (3, _("Low"))
	
class ESAIEnum(KeyValueBaseEnum):
	"""
	Enumeration for different ESAI values

	Args:
		enum ([type]): [description]

	Returns:
		[type]: [description]
	"""
	CRITICAL_C3 = (1, _("Critical_C3"))
	CRITICAL_C2 = (2, _("Critical_C2"))
	CRITICAL_C1 = (3, _("Critical_C1"))
	FRAGILE_F3 = (4, _("Fragile_F3"))
	FRAGILE_F2 = (5, _("Fragile_F2"))
	FRAGILE_F1 = (6, _("Fragile_F1"))
	POTENTIAL = (7, _("Potential"))
	NONAFFECTED = (8, _("Non affected"))

class ClimateQualityIndexEnum(KeyValueBaseEnum):
	"""
	Enumeration for different types of Climate Quality Index
	"""
	HIGH_QUALITY = (1, _("High"))
	MODERATE_QUALITY = (2, _("Moderate"))
	LOW_QUALITY = (3, _("Low"))
	
class SoilQualityIndexEnum(KeyValueBaseEnum):
	"""
	Enumeration for different types of Soil Quality Index
	"""
	HIGH_QUALITY = (1, _("High"))
	MODERATE_QUALITY = (2, _("Moderate"))
	LOW_QUALITY = (3, _("Low"))	

class SoilSlopeIndexEnum(KeyValueBaseEnum):
	"""
	Enumeration for different types of Soil Slope
	"""
	VERY_GENTLE_TO_FLAT = (1, _("Very gentle to flat"), 1)
	GENTLE = (2, _("Gentle"), 1.2)
	STEEP = (3, _("Steep"), 1.5)
	VERY_STEEP = (4, _("Very steep"), 2)	

	@property
	def index(self):
		return self.value[2]

class SoilGroupIndexEnum(KeyValueIndexBaseEnum):
	"""
	Enumeration for different types of Soil Group
	"""
	DEEP = (1, _("Deep"), 1)
	MODERATE = (2, _("Moderate"), 2)
	SHALLOW = (3, _("Shallow"), 3)
	VERY_SHALLOW = (4, _("Very shallow"), 4)	

class SoilDrainageIndexEnum(KeyValueIndexBaseEnum):
	"""
	Enumeration for different types of Soil Drainage
	"""
	WELL_DRAINED = (1, _("Well drained"), 1)
	IMPERFECTLY_DRAINED = (2, _("Imperfectly drained"), 1.2)
	POORLY_DRAINED = (3, _("Poorly drained"), 2)
	
class SoilParentMaterialEnum(KeyValueIndexBaseEnum):
	"""
	Enumeration for different types of Parent Material
	"""
	GOOD = (1, _("Good"), 1.0)
	MODERATE = (2, _("Moderate"), 1.7)
	POOR = (3, _("Poor"), 2.0)
	
class SoilTextureEnum(KeyValueIndexBaseEnum):
	"""
	Enumeration for different types of Soil Texture
	"""
	GOOD = (1, _("L, SCL, SL, LS, CL"), 1)
	MODERATE = (2, _("SC, SiL SiCL"), 1.2)
	POOR = (3, _("Si, C, SiC"), 1.6)
	VERY_POOR = (4, _("S"), 2)
	
	

class SoilRockFragmentEnum(KeyValueIndexBaseEnum):
	"""
	Enumeration for different types of Rock Fragments
	"""
	VERY_STONY = (1, _("Very stony"), 1)
	STONY = (2, _("Stony"), 1.3)
	BARE_TO_SLIGHTLY_STONY = (3, _("Bare to slightly stony"), 2)
		

class VegetationQualityEnum(KeyValueBaseEnum):
	"""
	Enumeration for different types of Vegetation Quality
	"""
	HIGH_QUALITY = (1, _("High Quality"))
	MODERATE_QUALITY = (2, _("Moderate Quality"))
	LOW_QUALITY = (3, _("Low Quality"))
	
class FireRiskEnum(KeyValueIndexBaseEnum):
	"""
	Enumeration for different types of Fire Risk Index
	"""
	LOW = (1, _("Low"), 1)
	MODERATE = (2, _("Moderate"), 1.3)
	HIGH = (3, _("High"), 1.6)
	VERY_HIGH = (4, _("Very High"), 2)
	
	
class ErosionProtectionEnum(KeyValueIndexBaseEnum):
	"""
	Enumeration for different types of Erosion Protection Index
	"""
	VERY_HIGH = (1, _("Very High"), 1)
	HIGH = (2, _("High"), 1.3)
	MODERATE = (3, _("Moderate"), 1.6)
	LOW = (4, _("Low"), 1.8)
	VERY_LOW = (5, _("Very Low"), 2)	
	

class DroughtResistanceEnum(KeyValueIndexBaseEnum):
	"""
	Enumeration for different types of Drought Resistance Index
	"""
	VERY_HIGH = (1, _("Very High"), 1)
	HIGH = (2, _("High"), 1.2)
	MODERATE = (3, _("Moderate"), 1.4)
	LOW = (4, _("Low"), 1.8)
	VERY_LOW = (5, _("Very Low"), 2)
	
class PlantCoverEnum(KeyValueIndexBaseEnum):
	"""
	Enumeration for different types of Plant Cover
	"""
	HIGH = (1, _("High"), 1)
	LOW = (2, _("Low"), 1.8)
	VERY_LOW = (3, _("Very low"), 2.0)
	
class ProductivityCalcEnum(enum.Enum):
	"""
	Enumeration for different types of Productivity computations
	"""
	TRAJECTORY = 0
	STATE = 1
	PERFORMANCE = 2
	PRODUCTIVITY = 3

class MedalusCalcEnum(enum.Enum):
	"""
	Enumeration for different types of Medalus computations
	"""
	ARIDITY_INDEX = 1
	CLIMATE_QUALITY_INDEX = 2
	SOIL_QUALITY_INDEX = 3
	MANAGEMENT_QUALITY_INDEX = 4
	VEGETATION_QUALITY_INDEX = 5
	ESAI = 6

class RasterSourceEnum(enum.Enum):
	"""
	Enumeration for different raster sources
	"""
	LULC = "LULC"
	MODIS = "Modis"
	LANDSAT7 = "Landsat 7"
	LANDSAT8 = "Landsat 8"
	HANSEN = "Hansen"
	SENTINEL2 = "Sentinel 2"
	# SINGLE_BAND_IMAGE = 1
	# MODIS = 2
	# LANDSAT7 = 3
	# LANDSAT8 = 4

class GenericRasterBandEnum(enum.Enum):
	"""
	Enumeration for raster bands independently of image source.
	Will be used to retrieve the correct band dynamically
	depending on the image source
	"""
	HAS_SINGLE_BAND = 0 # handles reading of images with only a single band
	RED = 1
	GREEN = 2
	BLUE = 3
	NIR = 4
	SWIR1 = 5
	SWIR2 = 6

class MODISBandEnum(enum.Enum):
	"""
	Enumeration for MODIS bands
	"""
	RED = 1
	NIR = 2
	BLUE = 3
	GREEN = 4
	SWIR1 = 5
	SWIR2 = 6

class Landsat7BandEnum(enum.Enum):
	"""
	Enumeration for Landsat 7 bands
	"""
	BLUE = 1
	GREEN = 2
	RED = 3
	NIR = 4
	SWIR1 = 5
	TIR = 6
	SWIR2 = 7
	PANCHROMATIC = 8

class Landsat8BandEnum(enum.Enum):
	"""
	Enumeration for Landsat 8 bands
	"""
	COASTAL = 1
	BLUE = 2
	GREEN = 3
	RED = 4
	NIR = 5
	SWIR1 = 6
	SWIR2 = 7
	PANCHROMATIC = 8
	CIRRUS = 9
	TIR1 = 10
	TIR2 = 11

class RasterOperationEnum(enum.Enum):
	"""Enumeration for different raster operations
	"""
	ADD = 1
	SUBTRACT = 2
	DIVIDE = 3
	MULTIPLY = 4

class RasterCategoryEnum(enum.Enum):
	"""Enumeration for different raster categories
	"""
	NDVI = "NDVI"
	LULC = "LULC"
	SOC = "SOC"
	RAINFALL = "Rainfall"
	ASPECT = "Aspect"
	FOREST_LOSS = "Forest Loss"
	SAVI = "SAVI"
	MSAVI = "MSAVI"
	EVAPOTRANSPIRATION = "Evapotranspiration"
	ECOLOGICAL_UNITS = "Ecological Units"
	SOIL_SLOPE = "Soil Slope"
	SOIL_GROUP = "Soil Group"
	SOIL_DRAINAGE = "Soil Drainage"
	SOIL_PARENT_MATERIAL = "Soil Parent Material"
	SOIL_TEXTURE = "Soil Texture"
	SOIL_ROCK_FRAGMENT = "Soil Rock Fragments"
	POPULATION_DENSITY = "Population Density"
	LAND_USE_DENSITY = "Land Use Density"
	FIRE_RISK = "Fire Risk"
	EROSION_PROTECTION = "Erosion Protection"
	DROUGHT_RESISTANCE = "Drought Resistance"
	PLANT_COVER = "Plant Cover"
	ARIDITY_INDEX = "Aridity Index"
	TREE_COVER_LOSS = "Tree Cover Loss"
	FOREST_ACTIVITY_MAP = "Forest Activity Map"
	VEGETATION_COVER = "Vegetation Cover"
	SOIL_ROUGHNESS = "Soil Roughness"
	SOIL_CRUST = "Soil Crust"
	ERODIBLE_FRACTION = "Erodible Fraction"
	CLIMATIC_EROSIVITY = "Climatic Erosivity"
	RAINFALL_EROSIVITY = "Rainfall Erosivity"
	SOIL_ERODIBILITY = "Soil Erodibility"
	SLOPE_STEEPNESS = "Slope Steepness"
	COVER_MANAGEMENT = "Cover Management"
	CONSERVATION_PRACTICES = "Conservation Practices"
	GEOMORPHOLOGY = "Geomorphology"
	COASTAL_SLOPE = "Coastal Slope"
	SEALEVEL_CHANGE = "Sea Level Change"
	SHORELINE_EROSION = "Shoreline Erosion/Accretion"
	TIDE_RANGE = "Tide Range"
	WAVE_HEIGHT = "Wave Height"

class ForestCoverLossQuinaryEnum(KeyValueBaseEnum):
	"""
	Enumeration for different Tree Cover Loss Map values
	"""
	NODATA = (0, _("No Data"))
	TREES_IN_BOTH_PERIODS = (1, _("Trees in both periods"))
	NO_TREES_IN_BOTH_PERIODS = (2, _("No tree canopy in both periods"))
	TREE_LOSS_IN_PERIOD1  = (3, _("Loss of tree presence in period 1"))	
	TREE_LOSS_IN_PERIOD2  = (4, _("Loss of tree presence in period 2"))

class ForestChangeTernaryEnum(KeyValueBaseEnum):
	"""
	Enumeration for different Forest Change values excluding NOT_FOREST
	"""
	# NODATA = (0, _("No Data"))
	UNDISTURBED_FOREST = (1, _("Undisturbed Forest"))
	DEGRADED_FOREST  = (2, _("Degraded Forest"))	
	DEFORESTED  = (3, _("Deforested"))	

class ForestChangeQuinaryEnum(KeyValueBaseEnum):
	"""
	Enumeration for different Forest Change values including NOT_FOREST
	"""
	UNDISTURBED_FOREST = (1, _("Undisturbed Forest"))
	DEGRADED_FOREST  = (2, _("Degraded Forest"))	
	DEFORESTED  = (3, _("Deforested"))	
	NOT_FOREST = (4, _("Not a forest"))
	
class ILSWEFactorsEnum(KeyValueBaseEnum):
	"""
	Enumeration for different types of ILSWE(RWEQ) Input factors
	"""
	VERY_LOW = (1, _("Very Low"))	
	LOW = (2, _("Low"))
	MODERATE = (3, _("Moderate"))
	HIGH = (4, _("High")) 
	VERY_HIGH = (5, _("Very High"))

class ILSWEEnum(KeyValueIndexBaseEnum):
	"""
	Enumeration for different types of ILSWE
	"""
	VERY_LOW = (1, _("Very Low"), 1)
	LOW = (2, _("Low"), 1.2)
	MODERATE = (3, _("Moderate"), 1.4)
	HIGH = (4, _("High"), 1.8)
	VERY_HIGH = (5, _("Very High"), 2)

class ILSWEComputationTypeEnum(KeyValueBaseEnum):
	"""
	Enumeration for different types of ILSWE (RWEQ) Computation Type
	""" 
	"""
	Vegetation cover sensitivity
	"""
	VEGETATION_COVER = (1, _("Vegetation Cover"))

	"""
	Soil crust sensitivity
	"""
	SOIL_CRUST = (2, _("Soil Crust"))
	
	"""	
	Roughness Length sensitivity
	"""
	SOIL_ROUGHNESS = (3, _("Soil Roughness"))

	"""
	Erodible fraction sensitivity
	"""
	ERODIBLE_FRACTION = (4, _("Erodible Fraction")) 
	
	"""
	Climate Erosivity sensitivity
	"""
	CLIMATE_EROSIVITY = (5, _("Climate Erosivity"))
	
	"""
	RWEQ Index
	"""
	ILSWE = (6, _("ILSWE")) 

class RUSLEEnum(KeyValueBaseEnum):
	"""
	Enumeration for different types of RUSLE
	"""
	VERY_SLIGHT = (1, _("Very Slight"))
	SLIGHT = (2, _("Slight"))
	MODERATE = (3, _("Moderate"))
	HIGH = (4, _("High")) 
	VERY_HIGH = (5, _("Very High"))

class RUSLEFactorsEnum(KeyValueBaseEnum):
	"""
	Enumeration for different types of RUSLE Input factors
	"""
	VERY_LOW = (1, _("Very Low"))	
	LOW = (2, _("Low"))
	MEDIUM = (3, _("Medium"))
	HIGH = (4, _("High")) 
	VERY_HIGH = (5, _("Very High"))

class RUSLEComputationTypeEnum(KeyValueBaseEnum):
	"""
	Enumeration for different types of RUSLE computations
	"""
	"""
	P factor
	"""
	RAINFALL_EROSIVITY = (1, _("Rainfall Erosivity"))

	"""
	K factor
	"""
	SOIL_ERODIBILITY = (2, _("Soil Erodibility"))
	
	"""	
	S factor
	"""
	SLOPE_STEEPNESS = (3, _("Slope Steepness"))

	"""
	C factor
	"""
	COVER_MANAGEMENT = (4, _("Cover Management")) 
	
	"""
	R factor
	"""
	CONSERVATION_PRACTICES = (5, _("Conservation Practices"))
	
	"""
	Rusle Index
	"""
	RUSLE = (6, _("Rusle"))	

class CVIFactorsEnum(KeyValueBaseEnum):
	"""
	Enumeration for different types of Coastal Vulnerability Index Input factors
	"""
	VERY_LOW = (1, _("Very Low"))	
	LOW = (2, _("Low"))
	MODERATE = (3, _("Moderate"))
	HIGH = (4, _("High")) 
	VERY_HIGH = (5, _("Very High"))

class CVIEnum(KeyValueBaseEnum):
	"""
	Enumeration for different types of Coastal Vulnerability Index
	"""
	VERY_LOW = (1, _("Very Low"))	
	LOW = (2, _("Low"))
	MODERATE = (3, _("Moderate"))
	HIGH = (4, _("High")) 
	VERY_HIGH = (5, _("Very High"))


class CVIComputationTypeEnum(KeyValueBaseEnum):
	"""
	Enumeration for different types of Coastal Vulnerability Index computations
	"""
	GEOMORPHOLOGY = (1, _("Geomorphology"))
	COASTAL_SLOPE = (2, _("Coastal Slope"))
	SEALEVEL_CHANGE = (3, _("Sea Level Change"))
	SHORELINE_EROSION = (4, _("Shoreline Erosion"))
	TIDE_RANGE = (5, _("Mean Tide Range"))
	WAVE_HEIGHT = (6, _("Mean Wave Height"))
	CVI = (7, _("Coastal Vulnerability Index"))	

class ComputationEnum(enum.Enum):
	"""Enumeration for different computation analysis
	"""
	LULC = "LULC"
	LULC_CHANGE = "LULC Change"
	FOREST_CHANGE = "Forest Change"
	FOREST_FIRE = "Forest Fire"
	FOREST_FIRE_RISK = "Forest Fire Risk"
	SOC = "SOC"
	PRODUCTIVITY_STATE = "Productivity State"
	PRODUCTIVITY_TRAJECTORY = "Productivity Trajectory"
	PRODUCTIVITY_PERFORMANCE = "Productivity Performance"
	PRODUCTIVITY = "Productivity"
	LAND_DEGRADATION = "Land Degradation"
	ARIDITY_INDEX = "Aridity Index"
	CLIMATE_QUALITY_INDEX = "Climate Quality Index"
	SOIL_QUALITY_INDEX = "Soil Quality Index"
	VEGETATION_QUALITY_INDEX = "Vegetation Quality Index"
	MANAGEMENT_QUALITY_INDEX = "Management Quality Index"
	ESAI = "ESAI"
	FOREST_CARBON_EMISSION = "Forest Carbon Emission"
	ILSWE = "ILSWE"
	RUSLE = "RUSLE"
	COASTAL_VULNERABILITY_INDEX = "Coastal Vulnerability Index"
