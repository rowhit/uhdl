import os
import shutil

from myhdl import toVerilog, toVHDL, traceSignals

from uhdl.cosim import CoSimulator
from uhdl.utils import cd
from uhdl.structures import CaselessDict


def merge_config(current, new):
    if not new:
        return current

    merged = CaselessDict(current)
    merged.update(new)

    return merged


class toMyHDL(object):
    """Used to provide a uniform API for simulating with myhdl rather than
    a backend.
    """
    def __init__(self, top, *args, **kwargs):
        self.top = top
        self.args = args
        self.kwargs = kwargs

    def __call__(self):
        if self.trace:
            #traceSignals.timescale = toMyHDL.timescale
            traceSignals.name = self.name
            gen = traceSignals(self.top, *self.args, **self.kwargs)
        else:
            gen = self.top(*self.args, **self.kwargs)

        return gen


_convspec = CaselessDict({
    #hdl: converter, extension
    'myhdl': (toMyHDL, None),
    'verilog': (toVerilog, 'v'),
    'vhdl': (toVHDL, 'vhd'),
    })


def get_convspec(conf):
    hdl = conf.pop('hdl')
    name = conf['name']
    converter, ext = _convspec[hdl]
    for k, v in conf.items():
        setattr(converter, k, v)

    files = []
    if ext:
        files.append(name)
        if not conf['no_testbench']:
            files.append('tb_'+name)

        files = [f+'.'+ext for f in files]

    return converter, files


class HW(object):
    """A Hardware module.

    Provides a uniform API for conversion and simulation of MyHDL Instances.

    Attributes:
        config(dict): Dictionary(:class:`~.CaselessDict`) containing
            the default config.

            Modifying this attribute will change the default argument values
            of the :meth:`.convert` and :meth:`sim()` methods.
    """

    config = {
        'name': None,
        'path': '.',
        'hdl': 'myhdl',
        'backend': 'myhdl',
        'timescale': '1ns/1ps',
        'tb': True,
        'trace': True,
    }

    def __init__(self, top, *args, **kwargs):
        """
        Args:
            top (function): A function which returns MyHDL generators.
            *args: Arguments for top.
            **kwargs: Keyword arguments for top.
        """
        self.top = top
        self.args = args
        self.kwargs = kwargs
        self.config = CaselessDict(self.__class__.config)
        self.config['name'] = top.__name__

    def convert(self, **kwargs):
        """Converts the top function to another HDL

        Note:
            VHDL conversion has not been implemented yet.

        Args:
            hdl(str, optional): The target language. Defaults to 'verilog'.

            path(str, optional): Destination folder. Defaults to current dir.

            name(str, optional): Top level instance name, and output file name.
                Defaults to `self.top.__name__`

            tb(bool, optional): Specifies whether a test bench should be
                created. Defaults to True.

            trace(bool, optional): Whether the testbench should dump all
                signal waveforms. Defaults to True.

            timescale(str, optional): Defaults to '1ns/1ps'
        """

        if 'hdl' not in kwargs:
            kwargs['hdl'] = 'verilog'

        conf = merge_config(self.config, kwargs)
        self._convert(conf)

    def _convert(self, conf):
        if conf['hdl'] == 'vhdl':
            raise NotImplementedError('VHDL conversion not implemented yet.')

        converter_conf = {
            'hdl': conf['hdl'],
            'name': conf['name'],
            'timescale': conf['timescale'],
            'no_testbench': not(conf['tb'] or conf['trace']),
            'trace': conf['trace']
        }

        converter, files = get_convspec(converter_conf)
        gen = converter(self.top, *self.args, **self.kwargs)

        dest_path = conf['path']
        if dest_path != '.':
            for f in files:
                shutil.copy(f, dest_path)
                os.remove(f)

        return gen, converter, files

    def sim(self, **kwargs):
        """Simulate the top function.

        Args:
            backend(str, optional): Simulation runner.
                Available options are 'myhdl', 'icarus' and 'modelsim'.
                Defaults to 'myhdl'.

            hdl(str): Target HDL for conversion before simulation.
            **kwargs: Optional arguments that :meth:`.convert` takes.

        Returns:
            Generator sequence if the backend is myhdl,

            :class:`myhdl.Cosimulation` object if the backend is a simulator.
        """
        #sane defaults for sim
        backend_name = kwargs.get('backend', 'myhdl')
        if backend_name and backend_name != 'myhdl':
            backend = CoSimulator.registry[kwargs['backend']]
            if 'hdl' not in kwargs:
                if len(backend.compilers) > 1:
                    raise ValueError('Must specify hdl for backend', backend)
                kwargs['hdl'] = list(backend.compilers)[0]

        conf = merge_config(self.config, kwargs)

        gen, converter, files = self._convert(conf)
        with cd(conf['path']):
            if conf['backend'] == 'myhdl':
                r = gen()
            else:
                backend = CoSimulator.registry[conf['backend']]
                r = backend.cosim_gen(conf['hdl'], files, converter.portmap)

        return r
