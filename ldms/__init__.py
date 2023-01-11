class ModelNotExistError(Exception):
    """Model does not exist"""
    pass

class AnalysisParamError(Exception):
    """Parameter for analysis error"""
    pass

class CacheParamError(Exception):
    """
    Invalid object to generate cache key
    """
    pass