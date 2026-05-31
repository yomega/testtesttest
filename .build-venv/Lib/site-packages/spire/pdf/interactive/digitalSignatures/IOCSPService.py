from enum import Enum
from plum import dispatch
from typing import TypeVar,Union,Generic,List,Tuple
from spire.pdf.common import *
from spire.pdf import *
from ctypes import *
import abc

class IOCSPService (abc.ABC) :
    """
    OCSP service interface.
    """
#
#    @abc.abstractmethod
#    def Generate(self ,checkedCertificate:'X509Certificate2',issuerCertificate:'X509Certificate2')->List['Byte']:
#        """
#    <summary>
#        Generate OCSP response.
#    </summary>
#    <param name="checkedCertificate">certificate to checked</param>
#    <param name="issuerCertificate">certificate of the issuer</param>
#    <returns>OCSP response which must conform to RFC 2560</returns>
#        """
#        pass
#


