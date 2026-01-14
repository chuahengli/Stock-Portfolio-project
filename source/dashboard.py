from datetime import date, datetime,timedelta
import os
import sqlite3
from config import settings
from source import db
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib as mpl
import mplcyberpunk

def setup():
    # Setup and configure default style and fontstyles
    mpl.style.use('cyberpunk')
    plt.rcParams['font.family'] = 'Georgia'
    plt.rcParams['font.size'] = 12

def asset_allocation_data(current_date:datetime):
    date_str = current_date.strftime('%Y-%m-%d')
    conn = sqlite3.connect(str(settings.MOOMOO_PORTFOLIO_DB_PATH))
    query = f"SELECT stocks,options,cash FROM portfolio_snapshots WHERE date = '{date_str}'"

    df = pd.read_sql_query(query, conn)
    print(df)
    return df

def plot_asset_allocation(df:pd.DataFrame):
       data = df.to_dict(orient='records')[0]
       # List of Labels and Values to plot pie
       labels = list(data.keys())
       values = list(data.values())
       total_assets= round(sum(values),2)
       # Legends to show % allocation instead of labels on pie
       legend_labels = [f'{label}: {((value / total_assets) * 100):.1f}%' for label, value in zip(labels, values)]
       
       fig, ax = plt.subplots(layout='constrained',figsize=(8, 5))
       wedges, texts = ax.pie(x=values,
                            startangle=90,
                            wedgeprops={'width': 0.2}
              )
       # Place Total Assets text in the middle of pie
       ax.text(0, 0,
              "Total Assets:\n",
              fontname='georgia',
              size=14,
              ha='center',
              )
       ax.text(0,-0.05,
              f"${total_assets}", 
              fontname='georgia',
              size=24,
              weight='bold',
              ha='center'
              )
       # Insert the legend
       ax.legend(wedges, legend_labels, loc="upper center", bbox_to_anchor=(0.5, 0),ncols=len(labels),columnspacing=0.75,frameon=False)
       plt.show()

def main():
        
    return 0

if __name__ == "__main__":
    main()