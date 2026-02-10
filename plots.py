import os
import logging

import numpy as np
from scipy import stats

import matplotlib
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors

import cartopy
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from cartopy.util import add_cyclic_point


def plot_lon_lat(plotfile, plotname,
    plot_params, field, symmetric=False, itime=0):

    logging.info(plotfile)

    states_provinces = cfeature.NaturalEarthFeature(
        category='cultural',
        name='admin_1_states_provinces_lines',
        scale='50m',
        facecolor='none')

    ax = plt.axes(projection=ccrs.PlateCarree())

    lon_values = field.lon.values
    lat_values = field.lat.values

    if 'levels' in plot_params:
        levels = np.array(plot_params['levels'])
    else:
        levels = np.linspace(
            plot_params['range_min'], plot_params['range_max'],
            plot_params['nlevel'], endpoint=True)
    if 'augment_levels' in plot_params:
        levels = sorted(np.append(
            levels, np.array(plot_params['augment_levels'])))

    if field.ndim == 3: 
        # field_values = np.clip(field.values[0,:,:], levels[0], levels[-1])
        # field_values = np.mean(field.values[:,:,:], axis=0)
        field_values = field.values[itime,:,:]
    else:
        # field_values = np.clip(field.values[:,:], levels[0], levels[-1])
        field_values = field.values[:,:]
        # field_values = field

    field_values, lon_values \
        = add_cyclic_point(field_values, coord=lon_values)

    print(lat_values.shape)
    print(lon_values.shape)
    print(field_values.shape)

    lon_mesh, lat_mesh \
        = np.meshgrid(lon_values, lat_values)

    # print(np.nanmin(field_values), np.nanmax(field_values))
    field_mean = np.nanmean(field_values)

    extend_option = 'both' if symmetric else 'max' 
    cmap_option = plt.cm.RdBu_r if symmetric else plt.cm.turbo

    cp = ax.contourf(lon_mesh, lat_mesh, field_values,
        levels, cmap=cmap_option, extend=extend_option,
        transform=ccrs.PlateCarree())

    # ax.gridlines()
    ax.set_facecolor('gray')
    if plot_params.get('coastlines', False):
        try:
            ax.coastlines()
            # ax.add_feature(cfeature.BORDERS)
            # ax.add_feature(states_provinces)
        except Exception as exc:
            logging.warning('Skipping coastlines/features: %s', exc)

    plt.title(plotname + ('  Mean %.2g' % field_mean))

    cbar = plt.colorbar(cp, orientation='horizontal', pad=0.05)

    if 'ticks' in plot_params:
        cbar.set_ticks(plot_params['ticks'])
    if 'tick_labels' in plot_params:
        cbar.ax.set_xticklabels(plot_params['tick_labels'])
    cbar.ax.tick_params(labelsize=6)

    png_file = os.path.join(plotfile) + '.png'
    pdf_file = os.path.join(plotfile) + '.pdf'
    plt.savefig(png_file, bbox_inches='tight', dpi=720)
    plt.savefig(pdf_file, bbox_inches='tight')
    plt.clf()
