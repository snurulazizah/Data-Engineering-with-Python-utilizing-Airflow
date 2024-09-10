from airflow import DAG
from airflow.operators.python import PythonOperator
import pandas as pd
from datetime import datetime
import glob
import sqlite3

# function
def clean_df(df):
    # transaction_date
    df['transaction_date'] = pd.to_datetime(df['transaction_date'], format = "%d.%m.%y %X")
    
    # channel
    channel_revert = {'c1': 'Internet Banking',
           'c2': 'Mobile Banking',
           'c3': 'EDC',
           'c4': 'ATM',
           'c5': 'QR'}
    df['channel'] = df['channel'].replace(channel_revert)   

    # type
    type_revert = {'d': 'Debit',
               'c': 'Credit'}
    df['type'] = df['type'].replace(type_revert)

    # amount
    df['amount'] = df['amount'].str.replace('$', '').astype('float64')

    # to category
    cat_column = ['type', 'channel', 'city', 'state_name']
    df[cat_column] = df[cat_column].astype('category')

    return df

def fetch_clean():
    # pwd
    # /home/{user}/airflow/dags
    database = '/home/irfancr/airflow/dags/db/transactions.db'
    conn = sqlite3.connect(database)
    files = glob.glob("/home/irfancr/airflow/dags/data_input_airflow/*.csv")

    df_list = []

    for file in files:
        trx = pd.read_csv(file)
        trx_clean = clean_df(trx)

        last_update = pd.read_sql_query("""
                  SELECT transaction_date 
                  FROM transactions
                  ORDER BY transaction_date DESC
                  LIMIT 1
                  """, con = conn)
    
        last_timestamp = last_update['transaction_date'].to_string(index=False)

        trx_clean_update = trx_clean[trx_clean['transaction_date'] > last_timestamp]

        if trx_clean_update.shape[0] != 0:
            df_list.append(trx_clean_update)
    
    return df_list

def report_generator(ti):

    df_list = ti.xcom_pull(task_ids = 'fetch_clean_task')

    for df in df_list:
        # Mengambil periode bulan, untuk nama file
        periode = df['transaction_date'].dt.to_period('M').unique()[0]

        # menghitung frequency
        freq_trx = pd.crosstab(index=df['channel'],
                               columns='Jumlah Transaksi'
                               ).sort_values(
                                    by = 'Jumlah Transaksi', 
                                    ascending = False)
        
        # menghitung total amount
        total_trx = pd.crosstab(index = df['channel'],
                                columns = 'Total Transaksi',
                                values = df['amount'],
                                aggfunc = 'sum'
                                ).sort_values(
                                    by = 'Total Transaksi', 
                                    ascending = False)
        
        # tahapan tambahan
        
        with pd.ExcelWriter(f'/home/irfancr/airflow/dags/report/{periode}.xlsx') as writer:
            freq_trx.to_excel(writer, sheet_name = 'Frequency')
            total_trx.to_excel(writer, sheet_name = 'Total Amount')
            print(f"Berhasil membuat report: report/{periode}.xlsx")

def df_to_db(ti):
    # koneksi ke database
    database = '/home/irfancr/airflow/dags/db/transactions.db'
    conn = sqlite3.connect(database)
    
    # mengambil df_list dari task fetch_clean_task
    df_list = ti.xcom_pull(task_ids = 'fetch_clean_task')

    for df in df_list:
        df.to_sql(name = 'transactions',
                    con = conn,
                    if_exists = 'append',
                    index = False)
        print("Done Created DB")

# fungsi baru
# def fungsi_baru():

with DAG("dss_dag", # Dag id
         start_date = datetime(2024, 8, 29), # Berjalan mulai 29
        #  schedule_interval = '*/5 * * * *', # setiap 5 menit
        schedule_interval = '@monthly', # setiap bulan
        catchup = False):
    
    fetch_clean_task = PythonOperator(
        task_id = 'fetch_clean_task',
        python_callable = fetch_clean
    )

    # task df_to_db
    df_to_db_task = PythonOperator(
        task_id = 'df_to_db_task',
        python_callable = df_to_db
    )

    # task df_to_db
    report_generator_task = PythonOperator(
        task_id = 'report_generator_task',
        python_callable = report_generator
    )

    # task_baru
    

    # task_a -> task_b -> task_c
    # fetch_clean_task >> df_to_db_task >> report_generator_task
    # task_a -> [task_b, task_c]
    fetch_clean_task >> [df_to_db_task, report_generator_task]

