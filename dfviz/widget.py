from bokeh import palettes
import pandas as pd
import panel as pn
from hvplot import hvPlot
from .sigslot import SigSlot
from .utils import pretty_describe, logger
from .fields import *


class MainWidget(SigSlot):
    """dfviz main interface, interactive plotting of dataframes

    This is designed to be viewed in a notebook or stand-alone web application.

    Parameters
    ----------
    data : dataframe
        Dask or pandas dataframe to be plotted

    Examples
    --------
    wid = MainWidget(df)
    wid.show()  # opens up new browser tab
    wid.panel   # in a notebook, will display interface in cell output
    """

    def __init__(self, data):
        # TODO: input kwargs to set widgets' initial state
        super().__init__()
        self.data = data
        self.dasky = hasattr(data, 'dask')
        self.control = ControlWidget(self.data)
        self.kwtext = pn.pane.Str(name='YAML')
        self.output = pn.Tabs(pn.Spacer(name='Plot'), self.kwtext)

        self.method = pn.widgets.Select(
            name='Plot Type', options=list(plot_requires))
        self.plot = pn.widgets.Button(name='Plot')
        plotcont = pn.Row(self.method, self.plot,
                          pn.layout.HSpacer())

        self._register(self.plot, 'plot_clicked', 'clicks')
        self._register(self.method, 'method_changed')

        self.connect('plot_clicked', self.draw)
        self.connect('method_changed', self.control.set_method)

        self.panel = pn.Column(plotcont, self.control.panel, self.output)

    def draw(self, *args):
        """Recreate the plot with current arguments

        Called by "Plot" button
        """
        kwargs = self.control.kwargs
        kwargs['kind'] = self.method.value
        self.kwtext.object = pretty_describe(kwargs)
        data = self.control.sample.sample_data(self.data)
        self._plot = hvPlot(data)(**kwargs)
        self.output[0] = pn.Row(*pn.pane.HoloViews(self._plot), name='Plot')
        fig = list(self.output[0][0]._models.values())[0][0]
        try:
            xrange = fig.x_range.start, fig.x_range.end
            yrange = fig.y_range.start, fig.y_range.end
            self.control.set_ranges(xrange, yrange)
        except AttributeError:
            # some plots (e.g., Table) don't have ranges
            pass


class ControlWidget(SigSlot):
    """Set of tabs controlling data and style options"""

    def __init__(self, df):
        super().__init__()
        npartitions = getattr(df, 'npartitions', 1)
        self.autoplot = False

        self.sample = SamplePane(npartitions)
        self.fields = FieldsPane(columns=list(df.columns))
        self.style = StylePane()
        self.panel = pn.Tabs(self.sample.panel, self.fields.panel,
                             self.style.panel,
                             background=(230, 230, 230))
        self._register(self.panel, 'tab_changed', 'active')
        self.connect('tab_changed', self.maybe_disable_axes)
        self.previous_kwargs = {}
        self.set_method('area')

    def maybe_disable_axes(self, tab):
        """When the style tab is selected, the calculated axes may be invalid"""
        # tab activated - if kwargs changed, disable ranges
        if self.panel[tab] is self.style.panel:
            if self.fields_kwargs != self.previous_kwargs:
                self.style.disable_axes()

    def set_ranges(self, xrange, yrange):
        """New plot ranges are available, so set the corresponding widgets"""
        # new plot - if kwargs changed since last plot, update ranges;
        # they should be enabled if they end up with a real range
        if self.fields_kwargs != self.previous_kwargs:
            self.style.set_ranges(xrange, yrange)
            self.previous_kwargs = self.fields_kwargs

    def set_method(self, method):
        """A new plot type was selected, so reset fields and style tabs"""
        self.method = method
        self.fields.setup(method)
        self.style.setup(method)
        self.set_ranges(None, None)

    @property
    def fields_kwargs(self):
        fields_kwargs = {k: v for k, v in self.fields.kwargs.items()
                         if v is not None}
        fields_kwargs.update(self.sample.kwargs)
        return fields_kwargs

    @property
    def kwargs(self):
        kwargs = self.style.kwargs
        kwargs.update(self.fields_kwargs)
        return kwargs


def make_option_widget(name, columns=[], optional=False, style=False):
    """Create a panel object for the names keyword argument

    The arguments are all options to pass to hvplot(), and may have
    correspondingly named widgets somewhere in the interface.
    """
    if name in ['multi_y', 'columns']:
        if name == 'multi_y':
            name = 'y'
        return pn.widgets.MultiSelect(options=columns, name=name)
    if name == 'color' and style:
        return pn.widgets.ColorPicker(name='color', value="#FFFFFF")
    if name == 'size' and style:
        return pn.widgets.IntSlider(name='size', start=3, end=65, value=12,
                                    step=2)
    if name in ['x', 'y', 'z', 'by', 'groupby', 'color', 'size', 'C']:
        options = ([None] + columns) if optional else columns
        return pn.widgets.Select(options=options, name=name)
    if name in ['stacked', 'colorbar', 'logx', 'logy', 'invert']:
        return pn.widgets.Checkbox(name=name, value=False)
    if name == 'legend':
        return pn.widgets.Select(
            name='legend', value='right',
            options=[None, 'top', 'bottom', 'left', 'right']
        )
    if name == 'alpha':
        return pn.widgets.FloatSlider(name='alpha', start=0, end=1, value=0.9,
                                      step=0.05)
    if name == 'cmap':
        return pn.widgets.Select(name='cmap', value='Viridis',
                                 options=list(palettes.all_palettes))
    if name == 'marker':
        return pn.widgets.Select(name='marker', value='o',
                                 options=list('s.ov^<>*+x'))
    if name == 'bins':
        return pn.widgets.IntSlider(name='bins', value=20, start=2, end=100)


class StylePane(SigSlot):
    """Options specific to "how" to plot"""

    def __init__(self):
        self.panel = pn.Row(pn.Spacer(), pn.Spacer(), name='Style')

    def setup(self, method):
        """Find set of options relevant to given plot type and make widgets"""
        allowed = ['alpha', 'legend'] + plot_allows[method]
        ws = [make_option_widget(nreq, style=True) for nreq in allowed
              if nreq in option_names]
        self.panel[0] = pn.Column(*ws, name='Style')
        self.panel[1] = pn.Column(
            pn.widgets.IntSlider(name='width', value=600, start=100, end=1200),
            pn.widgets.IntSlider(name='height', value=400, start=100, end=1200)
        )
        self.axes = [
            pn.widgets.FloatSlider(name=n, start=0, end=1, disabled=True)
            for n in ['x min', 'x max', 'y min', 'y max']
        ]
        self.panel[1].extend(self.axes)
        self.xrange, self.yrange = None, None

    def disable_axes(self):
        """Axes are invalid, so make them unselectable"""
        for ax in self.axes:
            ax.disabled = True
            ax.start = ax.value = ax.end = 0

    def set_ranges(self, xrange=None, yrange=None):
        """Axes ranges were calculated, so remake the range widgets

        Note either of the ranges can be None, e.g., for categorical axes,
        in which case we clear and disable the corresponding widgets.
        """
        ax1, ax2 = self.axes[:2]
        if xrange and xrange[0] is not None and xrange[1] is not None:
            ax1.start = ax2.start = ax1.value = xrange[0]
            ax1.end = ax2.end = ax2.value = xrange[1]
            ax1.disabled = False
            ax2.disabled = False
        else:
            ax1.disabled = True
            ax2.disabled = True
        ax1, ax2 = self.axes[2:]
        if yrange and yrange[0] is not None and yrange[1] is not None:
            ax1.start = ax2.start = ax1.value = yrange[0]
            ax1.end = ax2.end = ax2.value = yrange[1]
            ax1.disabled = False
            ax2.disabled = False
        else:
            ax1.disabled = True
            ax2.disabled = True

    @property
    def kwargs(self):
        kw = {p.name: p.value for p in self.panel[0]}
        kw.update({p.name: p.value for p in self.panel[1][:2]})
        xlim = [None, None]
        ylim = [None, None]
        for w in self.panel[1][2:]:
            if w.disabled:
                continue
            if 'x ' in w.name:
                xlim['max' in w.name] = float(w.value)
                kw['xlim'] = tuple(xlim)
            else:
                ylim['max' in w.name] = float(w.value)
                kw['ylim'] = tuple(ylim)
        return kw


class FieldsPane(SigSlot):
    """Select which columns of the data get used for which roles in plotting"""

    def __init__(self, columns):
        super().__init__()
        self.columns = columns
        self.panel = pn.Column(name='Fields')

    def setup(self, method='bar'):
        """Display field selector appropriate for the given plot type"""
        self.panel.clear()
        for req in plot_requires[method]:
            if req in field_names:
                w = make_option_widget(req, self.columns)
                self.panel.append(w)
        for nreq in plot_allows[method]:
            if nreq in field_names:
                w = make_option_widget(nreq, self.columns, True)
                self.panel.append(w)

    @property
    def kwargs(self):
        out = {p.name: p.value for p in self.panel}
        y = out.get('y', [])
        if isinstance(y, list) and len(y) == 1:
            out['y'] = y[0]
        return out


class SamplePane(SigSlot):
    """Global data selection options"""

    def __init__(self, npartitions):
        super().__init__()
        self.npartitions = npartitions

        self.sample = pn.widgets.Checkbox(name='Sample', value=False)
        op = ['Random', 'Head', 'Tail']
        if npartitions > 1:
            op.append('Partition')
        self.how = pn.widgets.Select(options=op, name='How')
        self.par = pn.widgets.Select()
        self.rasterize = pn.widgets.Checkbox(name='rasterize')
        self.persist = pn.widgets.Checkbox(name='persist')
        self.make_sample_pars('Head')

        self._register(self.sample, 'sample_toggled')
        self._register(self.how, 'how_chosen')

        self.connect('sample_toggled',
                     lambda x: setattr(self.how, 'disabled', not x) or
                     setattr(self.par, 'disabled', not x))
        self.connect('how_chosen', self.make_sample_pars)
        self.changed = False

        # set default value
        self.sample.value = npartitions > 1

        self.panel = pn.Column(
            pn.Row(self.sample, self.how, self.par),
            pn.Row(self.rasterize, self.persist),
            name='Control'
        )

    def sample_data(self, data):
        """Execute sampling selection on th data"""
        # TODO: keep sampled data and don't remake until parameters change
        if self.sample.value is False:
            return data
        if self.how.value == 'Head':
            return data.head(self.par.value)
        if self.how.value == 'Tail':
            return data.tail(self.par.value)
        if self.how.value == 'Partition':
            return data.get_partition(self.par.value)
        if self.how.value == 'Random':
            df = data.sample(frac=self.par.value / 100)
            if hasattr(df, 'npartitions'):
                df = df.map_partitions(pd.DataFrame.sort_index)
            else:
                df.sort_index(inplace=True)
            return df

    @property
    def kwargs(self):
        return {w.name: w.value for w in [self.rasterize, self.persist]}

    def make_sample_pars(self, manner):
        opts = {'Random': ('percent', [10, 1, 0.1]),
                'Partition': ('#', list(range(self.npartitions))),
                'Head': ('rows', [10, 100, 1000, 10000]),
                'Tail': ('rows', [10, 100, 1000, 10000])}[manner]
        self.par.name = opts[0]
        self.par.options = opts[1]
