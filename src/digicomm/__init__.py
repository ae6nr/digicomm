import numpy as np
import scipy.stats
from scipy.signal.windows import *
import datetime


def generateRandomBits(n_bits):
    '''
    Generates a numpy array of 0's and 1's.
    '''
    return np.random.randint(0,high=2,size=n_bits,dtype='int')


def bitsToSymbols(bits, M):
    '''
    Takes an array of bits and converts them to their corresponding symbols.
    M is the number of points in the constellation.
    e.g. 0101 0000 1111 1010 -> 5 0 15 10
    '''
    n = int(np.log2(M))
    nsym = int(len(bits)/n)
    symbols = np.zeros((nsym,),dtype='int')
    w = (2**np.arange(n-1,-1,-1)).astype('int')

    for i in range(0,nsym):
        symbols[i] = sum(bits[i*n:(i+1)*n] * w)

    return symbols


def symbolsToIq(syms, constellation):
    """
    Converts symbol indexes to complex values according to the given constellation
    """
    return constellation[syms]


def matchedFilter(x, p):
    """
    Given a signal x, performs matched filtering based on pulse shape p
    """
    return np.convolve(x,np.flip(np.conj(p)))


def symbolsToBits(syms, M):
    '''
    Takes a series of symbols and converts them to their corresponding bits.
    M is the number of points in the constellation.
    e.g. 5 0 15 10 -> 0101 0000 1111 1010
    '''
    n = int(np.log2(M))
    bits = np.zeros(len(syms)*n, dtype='int')
    for i in range(0,len(syms)):
        s = format(syms[i], '0'+str(n)+'b') # represent symbol as binary string
        for j in range(0,n):
            bits[i*n+j] = s[j]
    return bits


def calculateBer(b1,b2):
    """
    Calculates the number of nonzero elements in the difference of the two arrays, and computes the bit error rate
    """
    return np.count_nonzero(b1 - b2) / len(b1)


def noiseVariance(SNR, Eb):
    """
    Given an SNR in dB and an energy per bit Eb, calculate the noise variance N0.
    Note: This calculates Eb / gamma, where gamma is the SNR on a linear scale.
    """
    return Eb / (10 ** (SNR/10)) # calculates N0


def addNoise(iqs, **kwargs):
    '''
    adds additive white gaussian noise to an array of complex IQ samples
    in **kwargs, you must specify
        a. SNR (dB) and Eb (the energy per bit), or
        b. N0, the noise variance
    '''
    if 'SNR' and 'Eb' in kwargs.keys():
        SNR = kwargs['SNR']
        Eb = kwargs['Eb']
        N0 = noiseVariance(SNR, Eb)
    elif 'N0' in kwargs.keys():
        N0 = kwargs['N0']
    else:
        raise Exception("addNoise(): must specify N0 or SNR & Eb in kwargs.")

    var = N0 / 2
    nr = np.random.normal(scale=np.sqrt(var), size=(len(iqs),))
    ni = np.random.normal(scale=np.sqrt(var), size=(len(iqs),))
    return iqs + (nr + 1j*ni)


def addFrequencyOffset(iqs, nuT=0.0):
    '''
    Adds a frequency nuT in terms of cycles/sample.
    '''
    return iqs * np.exp(1j*2.0*np.pi*np.arange(0,len(iqs))*nuT)


def addPhaseOffset(iqs, phase=None):
    '''
    Adds a random phase to a list of complex values.
    If none is specifed, a random phase is chosen.
    '''
    if phase == None:
        phase = 2*np.pi*np.random.rand()
    return iqs * np.exp(1j*phase)


def phaseAmbiguity(rx,uw):
    '''
    Returns angle between received samples and the provided unique word.
    '''
    return np.angle(np.sum(rx*np.conj(uw)))


def phaseAmbiguityResolution(rx, rxuw, uw):
    '''
    Returns the received data with the phase ambiguity removed.
    rxuw are the received symbols corresponding to the unique word
    uw is the unique word itself
    '''
    a = phaseAmbiguity(rxuw,uw)
    return addPhaseOffset(rx, phase=-a)


def makeDecision(iq, constellation):
    '''
    returns the index of nearest constellation point
    '''
    return np.argmin(abs(constellation - iq))


def makeDecisions(iqs, constellation):
    '''
    returns the indexes of the nearest constellation points
    '''
    idxs = np.zeros(len(iqs), dtype='int8')
    for i in range(0,len(iqs)):
        idxs[i] = makeDecision(iqs[i], constellation)
    return idxs


def freqOffsetEstimation16Apsk(rx, mode='gauss'):
    '''
    Various methods for estimating a frequency offset when using a 16-APSK constellation
    Returns the normalized frequency offset in terms of cycles/sample
    Available modes:
        'coarse'
        'gauss'
        'interp_1'
        'interp_2'
    '''

    def nonLinearXform(z):
        zz_m = z * np.conj(z);
        zz_p = 12 * np.angle(z);
        return zz_m * np.exp(1j*zz_p);

    z = nonLinearXform(rx)
    Lfft = 2*len(z)
    ZZ = np.fft.fft(z,Lfft)
    PP2 = ZZ * np.conj(ZZ)
    idx_max = np.argmax(PP2)

    if idx_max >= Lfft/2:
        vhat2 = (idx_max-Lfft)/(Lfft*12)
    else:
        vhat2 = idx_max/(Lfft*12)

    II1 = abs(PP2[idx_max-1])
    II2 = abs(PP2[idx_max])
    II3 = abs(PP2[idx_max+1])
    II0 = np.maximum(II1, II3)

    if mode == 'interp_1':
        return vhat2 + 1/(12*Lfft) * 0.5*(II1-II3)/(II1-2*II2+II3) # D'Amico
    elif mode == 'interp_2':
        return vhat2 + np.sign(II3 - II1) / Lfft * II0 / (II2 - II0) / 2 / 2 / np.pi / 12
    elif mode == 'gauss':
        return vhat2 + ( (1 / Lfft) * (np.log(II1) - np.log(II3)) / (np.log(II1) - 2*np.log(II2) + np.log(II3)) ) / (24 * np.pi)
    elif mode == 'coarse':
        return vhat2
    else:
        raise Exception('Invalid mode.')


def freqOffsetEstimationQpsk(rx, mode='interp_2'):
    '''
    Various methods for estimating a frequency offset when using a QPSK constellation
    Returns the normalized frequency offset in terms of cycles/sample
    Available modes:
        'coarse'
        'gauss'
        'interp_1'
        'interp_2'
    Note: none of these have been derived from first princples. I modified the 16-APSK frequency estimators and they appear to work. There are probably more efficient/better frequency estimation methods available for QPSK. I simply haven't looked for them.
    '''

    def nonLinearXform(z):
        zz_m = z * np.conj(z);
        zz_p = 4 * np.angle(z);
        return zz_m * np.exp(1j*zz_p);

    z = nonLinearXform(rx)
    Lfft = 2*len(z)
    ZZ = np.fft.fft(z,Lfft)
    PP2 = ZZ * np.conj(ZZ)
    idx_max = np.argmax(PP2)

    if idx_max >= Lfft/2:
        vhat2 = (idx_max-Lfft)/(Lfft*4)
    else:
        vhat2 = idx_max/(Lfft*4)

    II1 = abs(PP2[idx_max-1])
    II2 = abs(PP2[idx_max])
    II3 = abs(PP2[idx_max+1])
    II0 = np.maximum(II1, II3)

    if mode == 'interp_1':
        return vhat2 + 1/(4*Lfft) * 0.5*(II1-II3)/(II1-2*II2+II3) # D'Amico
    elif mode == 'interp_2':
        return vhat2 + np.sign(II3 - II1) / Lfft * II0 / (II2 - II0) / 2 / 2 / np.pi / 4
    elif mode == 'gauss':
        return vhat2 + ( (1 / Lfft) * (np.log(II1) - np.log(II3)) / (np.log(II1) - 2*np.log(II2) + np.log(II3)) ) / (2 * 4 * np.pi)
    elif mode == 'coarse':
        return vhat2
    else:
        raise Exception('Invalid mode.')


def createDerivativeFilter(N=51,Tsamp=1):
    '''
    Calculates the coefficients for a derivative filter.
    N must be odd
    '''
    if (N+1)%4 != 0:
        raise Exception("createDerivativeFilter: N must be of form 4*n-1")
    ndmin = -(N-1)/2
    ndmax = (N-1)/2 
    nd = np.arange(ndmin, ndmax+1)
    d = np.zeros(nd.shape)
    ndnz = nd != 0 # nonzero indexes
    d[ndnz] = 1 / Tsamp * ((-1)**nd[ndnz]) / nd[ndnz]
    d = d * blackman(N)
    return d


def derivativeFilter2(x, N=51,Tsamp=1,zero_edge=False):
    '''
    Calculates the derivative of a discrete-time signal x with sample time Tsamp using a filter of length N.
    Because convolution results in values that are not correct near the edges, I decided to zero out those values as they can be quite large. So don't be surpised by the zeros at the beginning and end of the array.
    '''
    d = createDerivativeFilter(N=N,Tsamp=Tsamp)
    pad = int((N-1)/2) # this is the number of samples at the beginning/end of the signal that aren't quite correct due to blurring from convolution
    xd = (np.convolve(x,d))[pad:-pad]
    if zero_edge:
        xd[0:pad] = 0
        xd[-pad:-1] = 0
        xd[-1] = 0
    return xd


def derivativeFilter(x,N=51,Tsamp=1):
    '''
    Calculates the derivative of a discrete-time signal x with sample time Tsamp using a filter of length N.
    Because convolution results in values that are not correct near the edges, this function appends a linear extrapolation on either end prior to convolution to avoid strange filter behavior.
    This might not work well in the presence of even mild noise, but seems to work better than the original function I wrote.
    '''
    d = createDerivativeFilter(N=N,Tsamp=Tsamp)
    pad = int((N-1)/2) # this is the number of samples at the beginning/end of the signal that aren't quite correct due to blurring from convolution
    
    # extend x with linear extrapolation on both ends
    x2 = np.zeros((len(x)+2*pad,))
    x2[pad:-pad] = x # insert sequence in middle
    x2[0:pad] = x[0] - np.arange(pad,0,step=-1) * (x[1] - x[0]) # left side extrapolation
    x2[len(x2)-pad:len(x2)] = x[-1] + np.arange(1,pad+1) * (x[-1] - x[-2]) # right side extrapolation
    
    # valid values
    xd = (np.convolve(x2,d))[2*pad:-2*pad]
    return xd


def fractionalDelayCoeffs(T, dT, L):
    """
    Produces fractional delay filter coefficients.
    """
    n = np.arange(-L,L+1)
    x = (n+dT/T)*np.pi
    r = np.ones(x.shape)
    idxs = x != 0
    r[idxs] = np.sin(x[idxs]) / x[idxs]
    return r
    # return np.sin(x) / x


def fractionalDelayFilter(x,gamma,N=51):
    """
    Given a sampled signal x, delay by gamma samples, where gamma can be any float.
    N is the length of the filter used.
    """
    d = fractionalDelayCoeffs(1,gamma,N//2)
    pad = int((N-1)/2) # this is the number of samples at the beginning/end of the signal that aren't quite correct due to blurring from convolution
    
    # extend x with linear extrapolation on both ends
    x2 = np.zeros((len(x)+2*pad,))
    x2[pad:-pad] = x # insert sequence in middle
    x2[0:pad] = x[0] - np.arange(pad,0,step=-1) * (x[1] - x[0]) # left side extrapolation
    x2[len(x2)-pad:len(x2)] = x[-1] + np.arange(1,pad+1) * (x[-1] - x[-2]) # right side extrapolation
    
    # valid values
    xd = (np.convolve(x2,d))[2*pad:-2*pad]
    return xd


def rcosdesign(alpha, span, sps, Ts=1, shape='sqrt'):
    """
    Heavily modified from https://github.com/veeresht/CommPy/blob/master/commpy/filters.py
    Modified:
        -to return pulse with unit energy.
        -match MATLAB function call
        -return pulse shape of length span*Fs+1

    Generates a root raised cosine (RRC) filter (FIR) impulse response
    Parameters
    ----------
    alpha : float
        Roll off factor (Valid values are [0, 1]).
    span : int
        Number of symbols to span
    sps : int
        Samples per symbol
    Ts : float
        Symbol period in seconds.
    Returns
    ---------
    h : 1-D ndarray of floats
        Impulse response of the root raised cosine filter.
    time_idx : 1-D ndarray of floats
        Array containing the time indices, in seconds, for
        the impulse response.
    """

    N = span * sps
    T_delta = Ts/float(sps)
    time_idx = ((np.arange(N+1)-N/2))*T_delta
    sample_num = np.arange(N)
    h = np.zeros(N, dtype=float)

    if shape == 'sqrt':
        for x in sample_num:
            t = (x-N/2)*T_delta
            if t == 0.0:
                h[x] = 1.0 - alpha + (4*alpha/np.pi)
            elif alpha != 0 and t == Ts/(4*alpha):
                h[x] = (alpha/np.sqrt(2))*(((1+2/np.pi)* \
                        (np.sin(np.pi/(4*alpha)))) + ((1-2/np.pi)*(np.cos(np.pi/(4*alpha)))))
            elif alpha != 0 and t == -Ts/(4*alpha):
                h[x] = (alpha/np.sqrt(2))*(((1+2/np.pi)* \
                        (np.sin(np.pi/(4*alpha)))) + ((1-2/np.pi)*(np.cos(np.pi/(4*alpha)))))
            else:
                h[x] = (np.sin(np.pi*t*(1-alpha)/Ts) +  \
                        4*alpha*(t/Ts)*np.cos(np.pi*t*(1+alpha)/Ts))/ \
                        (np.pi*t*(1-(4*alpha*t/Ts)*(4*alpha*t/Ts))/Ts)
    elif shape == 'normal':
        for x in sample_num:
            t = (x-N/2)*T_delta
            if t == 0.0:
                h[x] = 1.0
            elif alpha != 0 and t == Ts/(2*alpha):
                h[x] = (np.pi/4)*(np.sin(np.pi*t/Ts)/(np.pi*t/Ts))
            elif alpha != 0 and t == -Ts/(2*alpha):
                h[x] = (np.pi/4)*(np.sin(np.pi*t/Ts)/(np.pi*t/Ts))
            else:
                h[x] = (np.sin(np.pi*t/Ts)/(np.pi*t/Ts))* \
                        (np.cos(np.pi*alpha*t/Ts)/(1-(((2*alpha*t)/Ts)*((2*alpha*t)/Ts))))    

    h = np.append(h, h[0])
    h = h / np.sqrt(h @ h) # normalize to unit energy

    return h, time_idx    


def qfunc(x):
    """
    Returns the area under the right tail [x,infinity) of the standard normal distribution.
    """
    return scipy.stats.norm.sf(x)


def lrecPulse(L,T,fsamp):
    """
    Rectangular Pulse shape for CPM (Table 3.3-1 of Proakis)
    L is span of pulse shape (number of symbols)
    T is the symbol time
    fsamp is the sampling frequency
    """
    leng = int(L*T*fsamp)
    t = np.linspace(0,L*T,num=leng)
    g = 1/(2*L*T) * np.ones((leng,))
    return g,t


def lrcPulse(L,T,fsamp):
    """
    Raised cosine pulse shape for CPM (Table 3.3-1 of Proakis)
    L is span of pulse shape (number of symbols)
    T is the symbol time
    fsamp is the sampling frequency
    """
    leng = int(L*T*fsamp)
    t = np.linspace(0,L*T,num=leng)
    g = 1/(2*L*T)*(1-np.cos(2*np.pi*t/(L*T))) * np.ones((leng,))
    return g,t


def gmskPulse(L, B, T, fsamp):
    """
    GMSK Pulse Shape for CPM (Table 3.3-1 of Proakis)
    L is span of pulse shape (number of symbols)
    B is bandwidth parameter
    T is symbol time
    fsamp is sampling frequency
    """
    t = np.arange(-L*T/2,L*T/2,step=1/fsamp) # sample instants
    g = (qfunc(2*np.pi*B*(t-T/2)) - qfunc(2*np.pi*B*(t+T/2))) / 2 / T # pulse shape
    return g,t


def zeroInsert(x,L):
    """
    Zero insertion with L-1 zeros between each sample.
    Update: no trailing zeros at the end.
    """
    z = np.zeros((len(x),L),dtype='complex')
    z[:,0] = x
    return z.flatten()[0:-(L-1)]


def upsample(x,p,L):
    """
    Upsample signal x by L, and convolve with p
    """
    train = zeroInsert(x,L)
    return np.convolve(train,p)


def wrap(t, A):
    """
    This returns the smallest difference between t and a multiple of 2*A.
    This may return a negative value.
    The graph looks like
        /    /    /   
       /    /    /
    --/----/----/--
     /    /    /
    /    /    /
    with extrema -A and A.
    """
    return np.mod(t+A, 2*A) - A
    

def timestampStr():
    """
    A simple timestamp function that returns the current date and time as a string.
    """
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")


def intToBinary(n, nbits):
    """
    n is an integer
    nbits is number of bits to use in the binary representation
    returns an numpy array of bits

    e.g.
    intToBinary(3,20) -> [0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 1 1]
    intToBinary(1, 4) -> [0 0 0 1]
    intToBinary(-1, 4) -> [1 1 1 1] # notice this is the same as below
    intToBinary(15, 4) -> [1 1 1 1] # notice this is the same as above
    """
    s = np.binary_repr(n,width=nbits)
    t = ("".join([c + "," for c in s]))[0:-1]
    return np.fromstring(t,dtype=int,sep=',')


def zeroCenteredArray(n):
    """ Produces an array of length n with increasing integers with a zero at the center """
    return np.arange(-(n-1)//2,(n-1)//2+1)
    

def arrayCenter(x,y):
    """
    Takes two numpy arrays.
    This function will return two values
    1. The first value returns the longer of the two arrays
    2. The second returns the shorter as an array padded with zeros on both ends so that it is the same length as the longer array.

    e.g.
    arrayCenter(
        np.array([1, 2, 3]),
        np.array([2, 3, 4, 5, 6]))
    -> (array([2, 3, 4, 5, 6]), array([0, 1, 2, 3, 0]))
    """
    n = len(x)
    m = len(y)

    if n < m:
        x, y = y, x
        n = len(x)
        m = len(y)

    z = np.zeros((n,))
    zi = (n-m)//2
    z[zi:zi+m] = y

    return x, z


def frequencyAxis(n, fs=1):
    """
    Returns the sample frequencies of a length-n FFT for a sequence with sample frequency fs.
    The DC component will be in the center of the array, not the beginning.
    """
    return zeroCenteredArray(n) / n * fs


def valleyFill(x, flip=False):
    if flip:
        return np.flip(valleyFill(np.flip(x)))
    else:
        x = np.copy(x)
        for i in range(len(x)-2,-1,-1):
            if x[i] < x[i+1]:
                x[i] = x[i+1]
        return x
    

def randomInRange(low=0, high=1):
    """
    Return a random value between [low, high) in the interval
    """
    return np.random.random() * (high - low) + low
