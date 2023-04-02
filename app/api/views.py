import datetime
import os

import pandas as pd
from http import HTTPStatus
from flask import jsonify, request
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity, create_refresh_token
from flask_restful import Resource
from sqlalchemy import create_engine
from werkzeug.security import check_password_hash


MYSQL_HOST = os.environ.get('MYSQL_HOST')
MYSQL_USER = os.environ.get('MYSQL_USER')
MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD')
MYSQL_DATABASE = os.environ.get('MYSQL_DATABASE')


class Login(Resource):
    def post(self):
        from app.models import Client
        client_id = request.json.get('client_id')
        secret = request.json.get('client_secret')
        client = Client.query.filter_by(id=client_id).first()
        if client:
            if check_password_hash(client.client_secret, secret):
                access_token = create_access_token(identity=client_id)
                refresh_token = create_refresh_token(identity=client_id)
                return jsonify(access_token=access_token, refresh_token=refresh_token)
            else:
                return {'message': 'Invalid API Key'}, HTTPStatus.UNAUTHORIZED
        else:
            return {'message': 'Client was not found.'}, HTTPStatus.NOT_FOUND


class RefreshToken(Resource):
    @jwt_required(refresh=True)
    def post(self):
        identity = get_jwt_identity()
        access_token = create_access_token(identity=identity)
        return jsonify(access_token=access_token)


class CMTEScore(Resource):
    @jwt_required()
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
        engine = create_engine(f'mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}/{MYSQL_DATABASE}')
        engine.connect()

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