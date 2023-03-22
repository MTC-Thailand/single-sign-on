import datetime
import os

import pandas as pd
from flask import jsonify, request
from flask_restful import Resource
from sqlalchemy import create_engine

MYSQL_HOST = os.environ.get('MYSQL_HOST')
MYSQL_USER = os.environ.get('MYSQL_USER')
MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD')
MYSQL_DATABASE = os.environ.get('MYSQL_DATABASE')

engine = create_engine(f'mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}/{MYSQL_DATABASE}')
engine.connect()


class CMTEScore(Resource):
    def get(self, lic_id):
        """
        This is a demo
        ---
        parameters:
            -   lic_id: license ID
                in: path
                type: string
                required: true
        responses:
            200:
                description: Sum of the CMTE scores of the individual
        """
        type_ = request.args.get('type', 'valid')
        if type_ == 'valid':
            query = f'''
            SELECT lic_mem.lic_exp_date, cpd_work.w_bdate, cpd_work.cpd_score FROM cpd_work INNER JOIN member ON member.mem_id=cpd_work.mem_id
            INNER JOIN lic_mem ON lic_mem.mem_id=member.mem_id
            WHERE lic_id={lic_id} AND cpd_work.w_bdate BETWEEN lic_mem.lic_b_date AND lic_mem.lic_exp_date
            '''
        elif type_ == 'total':
            query = f'''
            SELECT lic_mem.lic_exp_date, cpd_work.w_bdate, cpd_work.cpd_score FROM cpd_work INNER JOIN member ON member.mem_id=cpd_work.mem_id
            INNER JOIN lic_mem ON lic_mem.mem_id=member.mem_id
            WHERE lic_id={lic_id} 
            '''
        score = pd.read_sql_query(query, con=engine).cpd_score.sum()
        return jsonify({'data': {'scores': score,
                                 'type': type_,
                                 'datetime': datetime.datetime.now().isoformat()}})