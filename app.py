###########
# IMPORTS #
###########
from flask import Flask, render_template, request, redirect
import os

from bokeh.io import show, output_notebook, push_notebook
from bokeh.plotting import figure, show, output_file
from bokeh.models import LinearColorMapper, ColumnDataSource, ColorBar
from bokeh.models.callbacks import CustomJS
from bokeh.models.widgets import Select
from bokeh.models.tools import HoverTool
from bokeh.layouts import column
from bokeh.palettes import viridis
from bokeh.embed import components

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

###################
# FLASK FRAMEWORK #
###################

app = Flask(__name__)

app.vars={}
@app.route('/',methods=['GET','POST'])
def index():
    baseDF=getMap("Data/data_store/ESRI/London_Borough_Excluding_MHW.shp")
    tempDF1 = makeDF1(baseDF,"Data/00_FullDF.csv")
    tempPlot1 = plot1(tempDF1)

    tempDF2 = makeDF2(baseDF,"Data/00_FullDF.csv")
    tempPlot2 = plot2(tempDF2)

	
    script1, div1 = components(tempPlot1)
    script2, div2 = components(tempPlot2)		
    return render_template('index.html',tempScript1=script1,tempDiv1=div1,tempScript2=script2,tempDiv2=div2)


################
# GET MAP DATA #
################
# FUNCTIONS COPIED FROM HERE https://automating-gis-processes.github.io/2017/lessons/L5/advanced-bokeh.html
def getXYCoords(geometry, coord_type):
    """ Returns either x or y coordinates from  geometry coordinate sequence. Used with LineString and Polygon geometries."""
    if coord_type == 'x':
        return geometry.coords.xy[0]
    elif coord_type == 'y':
        return geometry.coords.xy[1]

def getPolyCoords(geometry, coord_type):
    """ Returns Coordinates of Polygon using the Exterior of the Polygon."""
    ext = geometry.exterior
    return getXYCoords(ext, coord_type)

def getLineCoords(geometry, coord_type):
    """ Returns Coordinates of Linestring object."""
    return getXYCoords(geometry, coord_type)

def getPointCoords(geometry, coord_type):
    """ Returns Coordinates of Point object."""
    if coord_type == 'x':
        return geometry.x
    elif coord_type == 'y':
        return geometry.y

def multiGeomHandler(multi_geometry, coord_type, geom_type):
    """
    Function for handling multi-geometries. Can be MultiPoint, MultiLineString or MultiPolygon.
    Returns a list of coordinates where all parts of Multi-geometries are merged into a single list.
    Individual geometries are separated with np.nan which is how Bokeh wants them.
    # Bokeh documentation regarding the Multi-geometry issues can be found here (it is an open issue)
    # https://github.com/bokeh/bokeh/issues/2321
    """

    for i, part in enumerate(multi_geometry):
        # On the first part of the Multi-geometry initialize the coord_array (np.array)
        if i == 0:
            if geom_type == "MultiPoint":
                coord_arrays = np.append(getPointCoords(part, coord_type), np.nan)
            elif geom_type == "MultiLineString":
                coord_arrays = np.append(getLineCoords(part, coord_type), np.nan)
            elif geom_type == "MultiPolygon":
                coord_arrays = np.append(getPolyCoords(part, coord_type), np.nan)
        else:
            if geom_type == "MultiPoint":
                coord_arrays = np.concatenate([coord_arrays, np.append(getPointCoords(part, coord_type), np.nan)])
            elif geom_type == "MultiLineString":
                coord_arrays = np.concatenate([coord_arrays, np.append(getLineCoords(part, coord_type), np.nan)])
            elif geom_type == "MultiPolygon":
                coord_arrays = np.concatenate([coord_arrays, np.append(getPolyCoords(part, coord_type), np.nan)])

    # Return the coordinates
    return coord_arrays


def getCoords(row, geom_col, coord_type):
    """
    Returns coordinates ('x' or 'y') of a geometry (Point, LineString or Polygon) as a list (if geometry is LineString or Polygon).
    Can handle also MultiGeometries.
    """
    # Get geometry
    geom = row[geom_col]

    # Check the geometry type
    gtype = geom.geom_type

    # "Normal" geometries
    # -------------------

    if gtype == "Point":
        return getPointCoords(geom, coord_type)
    elif gtype == "LineString":
        return list( getLineCoords(geom, coord_type) )
    elif gtype == "Polygon":
        return list( getPolyCoords(geom, coord_type) )

    # Multi geometries
    # ----------------

    else:
        return list( multiGeomHandler(geom, coord_type, gtype) )

def getMap(inFile):
    braw=gpd.read_file(inFile)        
    braw['x'] = braw.apply(getCoords, geom_col="geometry", coord_type="x", axis=1)
    braw['y'] = braw.apply(getCoords, geom_col="geometry", coord_type="y", axis=1)
    for i in range(len(braw)):
        braw.at[i,"x"],braw.at[i,"y"]=[val for val in braw.at[i,"x"] if str(val)!='nan'],[val for val in braw.at[i,"y"] if str(val)!='nan']
    return(braw)

#####################
# GET INCIDENT DATA #
#####################
def makeDF1(base,inFile):
    raw1=pd.read_csv(inFile)

    raw1=raw1.replace({'Staff...physically.injured': {'Yes': True, 'No': False, 'Unknown' : False},'Subject...injured.as.a.result.of.force.used': {'Yes': True, 'No': False, 'Unknown' : False}})
    raw1['Borough'] = raw1['Borough'].replace(['City of Westminster'], 'Westminster')

    val1DF=pd.DataFrame({'count' : raw1.groupby(["Borough"]).size()}).reset_index()

    full=base.merge(val1DF, left_on='NAME', right_on='Borough', how='left')[['x','y','Borough','count']]
    full['Borough'].fillna('City of London', inplace=True)

    #Get Data on what percent of indcidents tasers were used in
    raw1.Final_Effective_Tactic = raw1.Final_Effective_Tactic.str.replace(r'CED\s\(Taser\).*','Taser Involved')
    val2DF=raw1.groupby(["Borough", "Final_Effective_Tactic"]).size().reset_index(name="Taser_Count")
    val2DF=val2DF.loc[val2DF['Final_Effective_Tactic'] == 'Taser Involved']
    val2DF['Borough'] = val2DF['Borough'].replace(['City of Westminster'], 'Westminster')

    #Add val2 to full
    full2=full.merge(val2DF, on='Borough', how='left')[['x','y','Borough','count','Taser_Count']]
    full2['Taser_Per']=(full2.Taser_Count/full2['count'].std()*100).round(2)

    #Get data on what percent of incidents people got hurt in
    val3DF=pd.DataFrame({'Sub_Inj' : raw1.groupby('Borough')['Subject...injured.as.a.result.of.force.used'].sum(),
                    'Off_Inj' : raw1.groupby('Borough')['Staff...physically.injured'].sum()}).reset_index()

    #Add val3 to full
    full3=full2.merge(val3DF, on='Borough', how='left')[['x','y','Borough','count','Taser_Count','Taser_Per','Sub_Inj','Off_Inj']]
    full3['SubInj_Per'],full3['OffInj_Per']=(full3.Sub_Inj/full3['count'].std()*100).round(2),(full3.Off_Inj/full3['count'].std()*100).round(2)
    return(full3)
    
def makeDF2(base,inFile):
    raw1=pd.read_csv(inFile)
    
    raw1=raw1.replace({'Staff...physically.injured': {'Yes': True, 'No': False, 'Unknown' : False},'Subject...injured.as.a.result.of.force.used': {'Yes': True, 'No': False, 'Unknown' : False}})
    raw1['Borough'] = raw1['Borough'].replace(['City of Westminster'], 'Westminster')
    raw1['Borough'].fillna('City of London', inplace=True)
    
    val2DF=pd.DataFrame({'Crime_Rate' : raw1.groupby('Borough')['Crime.rate...Index'].mean(),
                     'Unemp_Rate' : raw1.groupby('Borough')['Unemployment.rate'].mean(),
                     'Delib_Fires' : raw1.groupby('Borough')['Deliberate.Fires'].mean(),
                     'Sub_WellBe' : raw1.groupby('Borough')['Subjective.well.being.average.score'].mean(),
                     'Avg_GCSE' : raw1.groupby('Borough')['Average.Capped.GCSE.and.Equivalent.Point.Score.Per.Pupil'].mean(),
                     'Pub_TransAcc' : raw1.groupby('Borough')['Public.Transport.Accessibility'].mean(),
                     'HateCrime_Rate' : raw1.groupby('Borough')['HateCrime_per1000'].mean(),
                     'Vote_Particip' : raw1.groupby('Borough')['Voting_Particip'].mean(),
                     'GreenSpace' : raw1.groupby('Borough')['Homes.with.access.to.open.space...nature..and...greenspace'].mean()
                    }).reset_index()
    full=base.merge(val2DF, left_on="NAME", right_on='Borough', how='left')[['x','y','NAME','Crime_Rate','Unemp_Rate','Delib_Fires','Sub_WellBe','Avg_GCSE','Pub_TransAcc','HateCrime_Rate','Vote_Particip','GreenSpace']]
    
    return(full)

###################
# PLOT WITH BOKEH #
###################

def plot1(inDF):
    colors=viridis(256)
    numColors = []
    colors2=viridis(30)
    perColors = []

    injColors_s=[]
    injColors_o=[]

    for borough in inDF['Borough']:
        try:
            val = inDF.loc[inDF['Borough'] == borough, 'count'].iloc[0]
            idxA, idxB = int(val/20), int(inDF.loc[inDF['Borough'] == borough, 'Taser_Per'].iloc[0])
            numColors.append(colors[idxA])
            perColors.append(colors2[idxB])
        
            idxC = int(inDF.loc[inDF['Borough'] == borough, 'SubInj_Per'].iloc[0])
            injColors_s.append(colors2[idxC])
            idxD = int(inDF.loc[inDF['Borough'] == borough, 'OffInj_Per'].iloc[0])
            injColors_o.append(colors2[idxD])
        except ValueError:
            numColors.append('grey')
            perColors.append('grey')
            injColors_s.append('grey')
            injColors_o.append('grey')

    inDF['Total Incidents']=numColors
    num_mapper = LinearColorMapper(palette=colors, low=inDF['count'].min(), high=inDF['count'].max())
    inDF['Taser Use Rate (%)']=perColors
    per_mapper = LinearColorMapper(palette=colors2, low=inDF['Taser_Per'].min(), high=inDF['Taser_Per'].max())
    inDF['Subject Injury Rate (%)']=injColors_s
    sub_mapper = LinearColorMapper(palette=colors2, low=inDF['SubInj_Per'].min(), high=inDF['SubInj_Per'].max())
    inDF['Officer Injury Rate (%)']=injColors_o
    off_mapper = LinearColorMapper(palette=colors2, low=inDF['OffInj_Per'].min(), high=inDF['OffInj_Per'].max())

    bars={"Total Incidents":num_mapper, "Taser Use Rate (%)":per_mapper,
     "Subject Injury Rate (%)":sub_mapper, "Officer Injury Rate (%)":off_mapper}

    #Create Data Source
    sourceD=ColumnDataSource(inDF)

    #Create Base Plot
    TOOLS = "pan,wheel_zoom,reset,hover,save"
    p = figure(plot_width=550, plot_height=550,
        title="Incident Outcomes by Borough", tools=TOOLS,
        x_axis_location=None, y_axis_location=None,
        tooltips=[
            ("Borough", "@Borough"), ("Number Incidents", "@count"), ("Taser Use Rate", "@Taser_Per"), ("Subject Injury Rate", "@SubInj_Per"), ("Officer Injury Rate", "@OffInj_Per"),
        ])
    p.grid.grid_line_color = None
    p.hover.point_policy = "follow_mouse"

    #Add elements
    r=p.patches('x', 'y', source=sourceD,
              fill_color='Total Incidents',
              fill_alpha=0.7, line_color="white", line_width=0.5)

    cb_cselect = CustomJS(args=dict(r=r,sourceD=sourceD,bars=bars), code ="""
        var selected_color = cb_obj.value;
        r.glyph.fill_color.field = selected_color;
        sourceD.change.emit()
    """)
    color_select = Select(title="Show:", value="Total Incidents", 
           options=["Total Incidents", "Taser Use Rate (%)",
                    "Subject Injury Rate (%)","Officer Injury Rate (%)"],
           callback=cb_cselect)
    layout = column(color_select, p)

    return(layout)

def plot2(full):
    colors=viridis(256)
    col_Colors=[]

    for datName in ['Crime_Rate','Unemp_Rate','Delib_Fires','Sub_WellBe','Avg_GCSE','Pub_TransAcc','HateCrime_Rate','Vote_Particip','GreenSpace']:
        colList=[]
        for borough in full['NAME']:
            try:
                val = full.loc[full['NAME'] == borough, datName].iloc[0]
                if datName=='HateCrime_Rate':
                    idx=int(val*55)
                elif datName=='Vote_Particip':
                    idx=int(val*200)
                else:
                    val = (val - full[datName].min()) * ((250-0)/(full[datName].max()-full[datName].min()))
                    idx = int(val)
                colList.append(colors[idx])
            except ValueError:
                colList.append('grey')
        col_Colors.append(colList)

    
    full['Crime Rate']=col_Colors[0]
    crime_mapper = LinearColorMapper(palette=colors, low=full['Crime_Rate'].min(), high=full['Crime_Rate'].max())
    full['Unemployment Rate']=col_Colors[1]
    unemp_mapper = LinearColorMapper(palette=colors, low=full['Unemp_Rate'].min(), high=full['Unemp_Rate'].max())
    full['Deliberate Fires Set']=col_Colors[2]
    fires_mapper = LinearColorMapper(palette=colors, low=full['Delib_Fires'].min(), high=full['Delib_Fires'].max())
    full['Subjective Well-Being Score']=col_Colors[3]
    swb_mapper = LinearColorMapper(palette=colors, low=full['Sub_WellBe'].min(), high=full['Sub_WellBe'].max())
    full['Average GCSE Score']=col_Colors[4]
    gcse_mapper = LinearColorMapper(palette=colors, low=full['Avg_GCSE'].min(), high=full['Avg_GCSE'].max())
    full['Public Transportation Accessibility']=col_Colors[5]
    transp_mapper = LinearColorMapper(palette=colors, low=full['Pub_TransAcc'].min(), high=full['Pub_TransAcc'].max())
    full['Hate Crime Rate']=col_Colors[6]
    hate_mapper = LinearColorMapper(palette=colors, low=full['HateCrime_Rate'].min(), high=full['HateCrime_Rate'].max())
    full['Voter Participation Rate']=col_Colors[7]
    particip_mapper = LinearColorMapper(palette=colors, low=full['Vote_Particip'].min(), high=full['Vote_Particip'].max())
    full['Homes with Access to Open Space and Nature']=col_Colors[8]
    green_mapper = LinearColorMapper(palette=colors, low=full['GreenSpace'].min(), high=full['GreenSpace'].max())	
	
    #~ full2=full.fillna(0)
    sourceD=ColumnDataSource(full)

    #Create Base Plot
    TOOLS = "pan,wheel_zoom,reset,hover,save"
    p = figure(plot_width=550, plot_height=550,
        title="Borough Descriptive Statistics", tools=TOOLS,
        x_axis_location=None, y_axis_location=None)
    p.grid.grid_line_color = None
    p.hover.point_policy = "follow_mouse"
    
	#Add elements
    r=p.patches('x', 'y', source=sourceD,
              fill_color='Crime Rate',
              fill_alpha=0.7, line_color="white", line_width=0.5)

    cb_cselect = CustomJS(args=dict(r=r,sourceD=sourceD), code ="""
        var selected_color = cb_obj.value;
        r.glyph.fill_color.field = selected_color;
        sourceD.change.emit()
        """)
    color_select = Select(title="Show:", value="Total Incidents", 
           options=['Crime Rate','Unemployment Rate','Deliberate Fires Set','Subjective Well-Being Score','Average GCSE Score',
           'Public Transportation Accessibility', 'Hate Crime Rate', 'Voter Participation Rate', 'Homes with Access to Open Space and Nature'],
           callback=cb_cselect)  
    layout = column(color_select, p)
	
    return(layout)

###############
# WRAPPING UP #
###############

@app.route('/about')
def about():
	return render_template('index.html')

if __name__ == "__main__":
	port = int(os.environ.get("PORT", 5000))
	app.run(host='0.0.0.0', port=port)
 

