from config import settings
from source import db

from datetime import date, datetime,timedelta
import sqlite3
import pandas as pd
import re
import plotly.express as px
import plotly.graph_objects as go
import yfinance as yf
import functools
import numpy as np





# Style Pandas dataframe
def style_negative_red_positive_green(val):
            color = '#A52A2A' if val < 0 else '#4CAF50'
            return f'color: {color}'

def asset_allocation_data(current_date:datetime):
    date_str = current_date.strftime('%Y-%m-%d')
    query = f"SELECT stocks,options,cash FROM portfolio_snapshots WHERE date = '{date_str}'"
    df = db.read_db(query)
    return df

def plot_asset_allocation(df: pd.DataFrame):
    df=df.copy().T
    df.columns = ['Value']    
    if df.empty:
        fig = go.Figure()
        fig.add_annotation(
            text="No Data Available for selected range",
            xref="paper", 
            yref="paper",
            x=0.5, 
            y=0.5, 
            showarrow=False,
            font=dict(size=20, color="gray")
        )
        fig.update_layout(
            template='plotly_dark',
            xaxis=dict(visible=False),
            yaxis=dict(visible=False)
        )
        return fig
    
    total_assets = df['Value'].sum()
    df['Legend_Label'] = [
        f"{idx}: {val/total_assets:.1%}" 
        for idx, val in zip(df.index, df['Value'])
    ]
    text_label = [f"${val:,.2f}" for val in df['Value']]
    fig = px.bar(df,
                x='Value',
                y=df.index,
                orientation='h',
                template='plotly_dark',
                color='Legend_Label',
                text=text_label,
                height=400
                )
    fig.update_layout(
                    xaxis=dict(automargin=True,visible=False),
                    yaxis=dict(tickfont=dict(size=14),automargin=True,title_text=""),
                    xaxis_range=[0, max(df['Value']) * 1.2],
                    title_text="",
                    font=dict(
                            size=14
                            ),
                    legend_title_text="Asset Breakdown",
                    legend={
                                'yanchor':"top",
                                'y':0.99,
                                'xanchor': "left",
                                'x': 0.9,
                                'font': {
                                        'size': 14
                                        },
                                'title': {
                                            'font': {
                                                    'size': 14
                                                    }    
                                        }
                            }
                    )
    fig.update_traces(textfont_size=14, textposition='outside',cliponaxis=False)
    return fig

def market_p_l_type(market: str):
    query = f"SELECT * FROM net_p_l"
    net_P_L = db.read_db(query)
    
    # Split by market 'US','SG','HK' etc.
    net_P_L = net_P_L[net_P_L['Market']==market].round(2)
    # If option
    option_pattern = r'[A-Z]+\d{6}[CP]\d+'
    # Column with Is_Option. 
    net_P_L['Is_Option'] = net_P_L['Symbol'].str.contains(option_pattern, regex=True)
    # New Column 'Ticker' according to if Option or not
    net_P_L['Ticker'] = net_P_L.apply(lambda x: get_base_ticker(x['Symbol'], x['Is_Option']), axis=1)
    # New column 'Asset Type' if is option, option gain, else stock gain
    net_P_L['Asset_Type'] = net_P_L['Is_Option'].map({True: 'Option', False: 'Stock'})


    # Create new dataframe with Ticker, Type, and Net_P_L
    pivot_df = net_P_L.pivot_table(index='Ticker', columns='Asset_Type', values='Net_P_L', aggfunc='sum').fillna(0)
    pivot_df['Total_Net_P_L'] = pivot_df.sum(axis=1)

    # Define which columns to round, checking if they exist first
    cols_to_round = [col for col in ['Stock', 'Option', 'Total_Net_P_L'] if col in pivot_df.columns]

    # Round the specified columns to 2 decimal places
    pivot_df[cols_to_round] = pivot_df[cols_to_round].round(2)

    return pivot_df

def get_base_ticker(symbol: str, is_opt):
    if is_opt:
        # For options, extract just the leading letters (e.g., 'AMZN' from 'AMZN260918C...')
        return re.match(r'^[A-Z]+', symbol).group()
    return symbol 

def get_twr(df: pd.DataFrame, start_date: datetime, end_date: datetime):
    start_str: str = start_date.strftime('%Y-%m-%d')
    end_str: str = end_date.strftime('%Y-%m-%d')

    try:
        beginning_nav = df.loc[df['date']==start_str,'nav'].values[0]
        end_nav = df.loc[df['date']==end_str,'nav'].values[0]
    except IndexError:
        return "N/A"

    returns = (end_nav-beginning_nav)/beginning_nav 
    twr = f"{returns:.2%}"
    return twr

def filter_portfolio_snapshots_df(df: pd.DataFrame, start_date: datetime, end_date: datetime):
    # Get 'date' and 'nav'
    twr_df = df.copy()
    # change date str column to datetime
    twr_df['date'] = pd.to_datetime(twr_df['date'])
    # Filter using a boolean mask
    mask = (twr_df['date'] >= start_date) & (twr_df['date'] <= end_date)
    filtered_df = twr_df.loc[mask].sort_values('date').reset_index(drop=True)
    return filtered_df

def config_plot_annotation(df: pd.DataFrame, label: str):
    x_anchor = "center"
    y_anchor = "middle"
    ax, ay = 0, 0
    if label == "Start":
        x_anchor = "right"  
        ax = -40            
    elif label == "End":
        x_anchor = "left"   
        ax = 40             
    elif label == "Peak":
        y_anchor = "bottom" 
        ay = -40            
    elif label == "Low":
        y_anchor = "top"    
        ay = 40
    return ax,ay,x_anchor,y_anchor


def config_datetime_axis_range(df: pd.DataFrame,y_metric: str, fig):
    # Extend x axis range for margin for annotation
    min_date = df['date'].min() - pd.Timedelta(days=round(len(df['date'])*0.2))
    max_date = df['date'].max() + pd.Timedelta(days=round(len(df['date'])*0.2))

    y_min = df[y_metric].min()
    y_max = df[y_metric].max()
    y_range = y_max - y_min
    buffer = y_range * 0.3 if y_range != 0 else 0.1
    fig.update_layout(
        yaxis_range=[y_min - buffer, y_max + buffer],
        xaxis_range=[min_date,max_date]
    )


def plot_asset_trend(df: pd.DataFrame, start_date: datetime, end_date: datetime, y_metric: str, type: str):
    # Cleanup to get things needed
    filtered_df = filter_portfolio_snapshots_df(df, start_date, end_date)
    # If dataframe empty, return empty plotly figure
    if filtered_df.empty:
        fig = go.Figure()
        fig.add_annotation(
            text="No Data Available for selected range",
            xref="paper", 
            yref="paper",
            x=0.5, 
            y=0.5, 
            showarrow=False,
            font=dict(size=20, color="gray")
        )
        fig.update_layout(
            template='plotly_dark',
            xaxis=dict(visible=False),
            yaxis=dict(visible=False)
        )
        return fig
    # If Time weighted Returns, 
    if type == 'twr':
        # Initial nav for first date to calculate change for annotation
        initial_nav = filtered_df['nav'].iloc[0]
        filtered_df[y_metric] = (filtered_df['nav'] / initial_nav) - 1

    fig = px.line(filtered_df, x='date', y=y_metric,
                template='plotly_dark', height=400)
    # Points to annotate
    point_indices = {
        "Start": filtered_df.index[0],
        "End": filtered_df.index[-1],
        "Peak": filtered_df[y_metric].idxmax(),
        "Low": filtered_df[y_metric].idxmin()
    }

    # Group labels by index to handle overlaps (e.g., End is also Peak)
    labels_by_index = {}
    for label, idx in point_indices.items():
        if idx not in labels_by_index:
            labels_by_index[idx] = []
        labels_by_index[idx].append(label)

    # Label unique points
    for idx, labels in labels_by_index.items():
        pt = filtered_df.loc[idx]
        
        # Determine the primary label for positioning logic (Peak/Low are most important)
        if 'Peak' in labels:
            primary_label = 'Peak'
        elif 'Low' in labels:
            primary_label = 'Low'
        elif 'End' in labels:
            primary_label = 'End'
        else:
            primary_label = 'Start'

        ax, ay, x_anchor, y_anchor = config_plot_annotation(filtered_df, primary_label)
        
        # Combine labels for display text in a consistent order
        display_text = " / ".join(sorted(labels, key=lambda x: ['Start', 'Low', 'Peak', 'End'].index(x)))
        
        fig.add_annotation(
                    x=pt['date'],
                    y=pt[y_metric],
                    text=f"<b>{display_text}</b><br>{pt[y_metric]:.2%}" if type == 'twr' else f"<b>{display_text}</b><br>{pt[y_metric]:,.2f}",
                    showarrow=False,
                    ax=ax,
                    ay=ay,
                    xanchor=x_anchor,
                    yanchor=y_anchor,
                    font={'size': 14},
                    opacity=0.7,
                    align="center"
                )
    # Configure axis ranges to prevent cut off from containers
    config_datetime_axis_range(filtered_df,y_metric,fig)
    fig.update_layout(
                        xaxis=dict(automargin=True,tickfont=dict(size=16),title="",
                                   showgrid=True,gridcolor='rgba(255,255,255,0.1)',showticklabels=True,
                                   rangeslider_visible=True,
                                   rangeselector=dict(
                                                        buttons=list([
                                                            dict(count=1, label="1m", step="month", stepmode="backward"),
                                                            dict(count=6, label="6m", step="month", stepmode="backward"),
                                                            dict(count=1, label="YTD", step="year", stepmode="todate"),
                                                            dict(count=1, label="1y", step="year", stepmode="backward"),
                                                            dict(step="all")
                                                        ])
                                                    )      
                                    ),
                        yaxis=dict(automargin=True,visible=False) if type == 'twr' else 
                            dict(automargin=True,title="",showgrid=True,gridcolor='rgba(255,255,255,0.1)',showticklabels=True,tickfont=dict(size=16))
                        )
    return fig

# Modify positions table to add the most information, to be filtered in other functions for displaying graphs and tables
def display_pos(df: pd.DataFrame):
    pos_df = df.copy()
    # Add column is option or not
    option_pattern = r'[A-Z]+\d{6}[CP]\d+'
    pos_df['Is_Option'] = pos_df['Symbol'].str.contains(option_pattern, regex=True)
    # Identify what Ticker, and if is option or stock
    pos_df['Ticker'] = pos_df.apply(lambda x: get_base_ticker(x['Symbol'], x['Is_Option']), axis=1)
    pos_df['Asset_Type'] = pos_df['Is_Option'].map({True: 'Option', False: 'Stock'})

    # Grouping and Sorting: Calculate total portfolio % per ticker to sort groups by size
    # Convert 'Portfolio_Percent' (e.g., "12.5%") to float for calculation
    pos_df['Sort_Val'] = pos_df['Portfolio_Percent'].astype(str).str.rstrip('%').astype(float)
    # Create new dataframe with each Ticker total percentage allocation for each ticker sum it 
    ticker_totals = pos_df.groupby('Ticker')['Sort_Val'].sum().reset_index(name='Ticker_Total_Val')
    # Merge onto Ticker column to match respective ticker, total ticker percentage on resepective ticker regardless option or stock
    pos_df = pos_df.merge(ticker_totals, on='Ticker')
    # Sort by each Ticker Total (desc), then by individual position value within each Ticker (desc)
    pos_df = pos_df.sort_values(by=['Ticker_Total_Val', 'Sort_Val'], ascending=[False, False])
    pos_df['Market_Cap'] = pos_df['Ticker'].apply(lambda x: get_mktcap(x))
    return pos_df

def style_pos(pos_df: pd.DataFrame):
    # Reorder columns to show Ticker and Asset Type first
    cols_order = ['Ticker', 'Asset_Type'] + [c for c in pos_df.columns if c not in ['Ticker', 'Symbol', 'Asset_Type', 'Is_Option', 'Sort_Val', 'Ticker_Total_Val', 'Market_Cap','date']]
    pos_df_styled = pos_df[cols_order]
    # Rename
    pos_df_styled = pos_df_styled.rename(
        columns={
                'Asset_Type': 'Asset Type',
                'Market_Value': 'Market Value',
                'Diluted_Cost': 'Diluted Cost',
                'Current_Price': 'Price',
                'P_L_Percent': 'P/L %',
                'P_L': 'P/L',
                'Today_s_P_L': 'Today\'s P/L',
                'Portfolio_Percent': 'Portfolio %'
        }
    )
    # Chain styling: apply color based on numeric value first, then format for display.
    return pos_df_styled.style.map(
        style_negative_red_positive_green, subset=['P/L %', 'P/L', "Today's P/L"]
    ).format({
        'Quantity': '{:,.2f}', 'Price': '{:,.3f}', 'Market Value': '{:,.2f}',
        'Diluted Cost': '{:,.3f}', 'P/L %': '{:+,.2f}%', 'P/L': '{:+,.2f}',
        "Today's P/L": '{:+,.2f}'
    }).hide(axis="index")
'''
        # Display positions dataframe
        st.dataframe(pos_df_styled, hide_index=True,
                     column_config={'date': None,
                                    'Asset_Type': 'Asset Type',
                                    'Symbol': None,
                                    'Quantity': st.column_config.NumberColumn('Quantity',
                                                                                  format="localized"),
                                    
                                    'Diluted_Cost': st.column_config.NumberColumn('Diluted Cost',
                                                                                  format="localized"),                                      
                                    'Market_Value': st.column_config.NumberColumn('Market Value',
                                                                                  format="localized"),
                                    'Current_Price': st.column_config.NumberColumn('Current Price',
                                                                                  format="localized"),
                                    'P_L_Percent': st.column_config.NumberColumn('P/L %',
                                                                                  format="%.2f %%"),
                                    'P_L': st.column_config.NumberColumn('P/L',
                                                                                  format="localized"),
                                    'Today_s_P_L': st.column_config.NumberColumn('Today\'s P/L',
                                                                                  format="localized"),
                                    'Portfolio_Percent': st.column_config.NumberColumn('Portfolio %',
                                                                                  format="percent"),
                                    'Market_Cap': None
                                    } 
                    )
        '''
'''
# Ticker allocation, with options and stocks summed in one ticker
def plot_pos(pos_df: pd.DataFrame):
    plot_df = pos_df.copy().groupby(['Ticker','Ticker_Total_Val'])['Market_Value'].sum().reset_index()
    plot_df.sort_values(by='Market_Value', inplace=True, ascending=True)
    plot_df = plot_df.round({
                                'Market_Value': 3,
                                'Ticker_Total_Val': 2
                            })
    text_label = [f"${val:,.2f} ({p/100: .2%})" for val, p in zip(plot_df['Market_Value'],plot_df['Ticker_Total_Val'])]
    fig = px.bar(plot_df, x='Market_Value', y='Ticker', orientation='h',
            template='plotly_dark',
            title="",
            height=600,
            text= text_label)
    fig.update_traces(textfont_size=14, textposition='outside',cliponaxis=False)
    fig.update_layout(
                    xaxis=dict(automargin=True),
                    yaxis=dict(tickfont=dict(size=14),automargin=True),
                    xaxis_range=[0, max(plot_df['Market_Value']) * 1.2],
                    showlegend=False,
                    font=dict(
                        size=14
                        )
                    )
    fig.update_yaxes(type='category',title_text="")
    fig.update_xaxes(title_text="",showticklabels=False, visible=False)
    return fig
'''
# Get sector of ticker symbol passed in via yfinance
@functools.lru_cache(maxsize=30)
def get_sector(ticker_symbol,month_tag: datetime = datetime.now().strftime("%Y-%m")):
    try:
        ticker = yf.Ticker(ticker_symbol)
        info = ticker.info
        
        # Check if it's an ETF. Then use the industry as the sector
        quote_type = info.get('quoteType', 'UNKNOWN')
        
        if quote_type == 'ETF':
            sector = info.get('category', info.get('fundFamily', 'Index/Fund'))
            # Attempt to get the category or fund family for the industry column
            industry = info.get('category', info.get('fundFamily', 'Index/Fund'))
        else:
            sector = info.get('sector', 'Other')
            industry = info.get('industry', 'Other')
            
        return sector, industry
    except Exception:
        return 'Unknown', 'Unknown'
# Sector allocation based on each position allocation
def plot_sector_allocation(pos_df: pd.DataFrame):
    # Group Ticker and that Ticker's total percentage alloc, sum market value
    sector_df = pos_df.copy().groupby(['Ticker','Ticker_Total_Val'])['Market_Value'].sum().reset_index()
    sector_df.sort_values(by='Market_Value', inplace=True, ascending=False)
    sector_df = sector_df.round({
                                'Market_Value': 3,
                                'Ticker_Total_Val': 2
                            })
    # Use yfinance to map sectors and industry
    sector_map = {}
    for ticker in sector_df['Ticker']:
        sector_map[ticker] = get_sector(ticker)

    sector_df['Sector'] = sector_df['Ticker'].map(lambda x: sector_map[x][0])
    sector_df['Industry'] = sector_df['Ticker'].map(lambda x: sector_map[x][1])
    # Group sector and get each sector percentage alloc
    sector_df= sector_df.groupby(['Sector'])['Ticker_Total_Val'].sum().reset_index().sort_values(by="Ticker_Total_Val", ascending=True)

    text_label = [f"{p/100: .2%}" for p in sector_df['Ticker_Total_Val']]
    fig_sector = px.bar(sector_df, x='Ticker_Total_Val', y='Sector', orientation='h',
                template='plotly_dark',text=text_label,height=400)
    fig_sector.update_layout(
                        xaxis=dict(automargin=True),
                        yaxis=dict(tickfont=dict(size=14),automargin=True),
                        xaxis_range=[0, max(sector_df['Ticker_Total_Val']) * 1.2],
                        showlegend=False,
                        font=dict(
                            size=14
                            ),
                        title= dict(
                                    text="Sector",
                                    font=dict(
                                                size=24
                                                )
           
                                                        
                                            )
                        )
    fig_sector.update_traces(textfont_size=14, textposition='outside',cliponaxis=False)
    fig_sector.update_yaxes(type='category',title_text="")
    fig_sector.update_xaxes(visible=False)
    return fig_sector
    
def positions_overview(pos_df: pd.DataFrame):
    pos_copy_df = pos_df.copy()

    # Group by Ticker and percentage alloc. Sum Market Value, Today's P/L and Total P/L
    position_overview = pos_copy_df.groupby(['Ticker','Ticker_Total_Val'])[['Market_Value','Today_s_P_L','P_L']].sum().reset_index()
    
    # Get prices for stocks present in portfolio
    prices_df = pos_copy_df.loc[pos_copy_df['Is_Option'] == False, ['Ticker', 'Current_Price']].drop_duplicates(subset=['Ticker'])
    
    # Identify tickers that only have options (missing from prices_df)
    existing_tickers = set(prices_df['Ticker'])
    all_tickers = set(position_overview['Ticker'])
    missing_tickers = list(all_tickers - existing_tickers)
    # Add missing tickers into prices_df with updated price from yfinance
    if missing_tickers:
        new_prices = []
        for ticker in missing_tickers:
            try:
                # Use fast_info for better performance on single attributes
                price = yf.Ticker(ticker).fast_info['last_price']
                new_prices.append({'Ticker': ticker, 'Current_Price': price})
            except Exception:
                new_prices.append({'Ticker': ticker, 'Current_Price': 0.0})
        
        if new_prices:
            prices_df = pd.concat([prices_df, pd.DataFrame(new_prices)], ignore_index=True)
    # Add current price column to overview
    position_overview = position_overview.merge(prices_df, on='Ticker', how='left')

    # Condition for if option
    condition = pos_copy_df['Is_Option'] == False
    # Multiply cost and quantity, if shares, if not shares multiply by another 100, create to column Total Cost for more accurate P/L % calc
    pos_copy_df['Total_Cost'] = np.where(
        condition,
        pos_copy_df['Diluted_Cost'] * pos_copy_df['Quantity'], # If True (Not an option)
        pos_copy_df['Diluted_Cost'] * pos_copy_df['Quantity'] * 100 # If False (Is an option)
    )
    # Group by Ticker and sum for each Ticker, total cost of stock and options of same ticker
    total_cost_df = pos_copy_df.groupby('Ticker')['Total_Cost'].sum().reset_index()
    position_overview = position_overview.merge(total_cost_df, on='Ticker')
    # Create P/L % column using Total_Cost
    position_overview['P_L_Percent'] = (position_overview['P_L'] / position_overview['Total_Cost'])
    # Set column order and remove Total_Cost column
    cols_order = ['Ticker','Market_Value','Current_Price','P_L_Percent','P_L','Today_s_P_L','Ticker_Total_Val']
    # Reorder columns
    position_overview = position_overview[cols_order]
    position_overview.sort_values(by='Ticker_Total_Val', inplace=True, ascending=False)
    # Style using colour, green for positive red for negative for subset of columns
    position_overview = position_overview.style.map(style_negative_red_positive_green, subset=['P_L', 'Today_s_P_L','P_L_Percent'])
    return position_overview

@functools.lru_cache(maxsize=30)
def get_mktcap(ticker: str,month_tag: datetime = datetime.now().strftime("%Y-%m")):
    return yf.Ticker(ticker).info.get('marketCap')
def market_cap_class(market_cap: float):
    if market_cap > 200000000000:
        return 'Mega'
    elif market_cap > 10000000000:
        return 'Large'
    elif market_cap > 2000000000:
        return 'Mid'
    elif market_cap > 300000000:
        return 'Small'
    elif market_cap > 50000000:
        return 'Micro'
    else:
        return 'Nano'
    
def plot_mktcap(pos_df: pd.DataFrame):
    market_cap_df = pos_df.copy().loc[:,['Ticker','Ticker_Total_Val','Market_Cap']].drop_duplicates().dropna()
    market_cap_df['Market_Cap_Cat'] = market_cap_df['Market_Cap'].apply(market_cap_class)
    market_cap_df = market_cap_df.groupby(['Market_Cap_Cat'])['Ticker_Total_Val'].sum().reset_index()
    market_cap_df.sort_values(by='Ticker_Total_Val',inplace=True)
    text_label = [f"{p/100: .2%}" for p in market_cap_df['Ticker_Total_Val']]
    fig_mktcap = px.bar(market_cap_df, x='Ticker_Total_Val', y='Market_Cap_Cat', orientation='h',
                    template='plotly_dark',text=text_label,height=400)
    fig_mktcap.update_layout(
                        xaxis=dict(automargin=True),
                        yaxis=dict(tickfont=dict(size=14),automargin=True),
                        xaxis_range=[0, max(market_cap_df['Ticker_Total_Val']) * 1.2],
                        showlegend=False,
                        font=dict(
                            size=14
                            ),
                        title= dict(
                                    text="Market Cap",
                                    font=dict(
                                                size=24
                                                )       
                                            )
                        
                        )
    fig_mktcap.update_traces(textfont_size=14, textposition='outside',cliponaxis=False)
    fig_mktcap.update_yaxes(type='category',title_text="")
    fig_mktcap.update_xaxes(visible=False)
    return fig_mktcap

@functools.lru_cache(maxsize=30)
def get_country(ticker: str,month_tag: datetime = datetime.now().strftime("%Y-%m")):
    tk = yf.Ticker(ticker).info
    try: 
        return tk['country']
    except Exception as e:
        return None
def plot_geog(pos_df: pd.DataFrame):
    geog_df = pos_df.copy().loc[:,['Ticker','Ticker_Total_Val']].drop_duplicates().dropna()
    geog_df['Country'] = geog_df['Ticker'].apply(lambda x: get_country(x))
    geog_df = geog_df.groupby(['Country'])['Ticker_Total_Val'].sum().reset_index()
    geog_df.sort_values(by='Ticker_Total_Val',inplace=True)

    text_label = [f"{p/100: .2%}" for p in geog_df['Ticker_Total_Val']]
    fig_geog = px.bar(geog_df, x='Ticker_Total_Val', y='Country', orientation='h',
                    template='plotly_dark',text=text_label,height=400)
    fig_geog.update_layout(
                        xaxis=dict(automargin=True),
                        yaxis=dict(tickfont=dict(size=14),automargin=True),
                        xaxis_range=[0, max(geog_df['Ticker_Total_Val']) * 1.2],
                        showlegend=False,
                        font=dict(
                            size=14
                            ),
                        title= dict(
                                    text="Geography",
                                    font=dict(
                                                size=24
                                                )           
                                    )
                        )
    fig_geog.update_traces(textfont_size=14, textposition='outside',cliponaxis=False)
    fig_geog.update_yaxes(type='category',title_text="")
    fig_geog.update_xaxes(visible=False)
    return fig_geog


def main():
        
    return 0

if __name__ == "__main__":
    main()