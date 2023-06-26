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


class MemberInfo(Resource):
    @jwt_required()
    def get(self, pid):
        engine = create_engine(f'mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}/{MYSQL_DATABASE}')
        engine.connect()
        query = f'''
        SELECT member.mem_id_txt,member.mem_id,member.title_id,member.fname,member.lname,member.e_title,member.e_fname,member.e_lname,
        emp_function.function_name,emp_owner.emp_owner_name,emp_contract.contract_name,member.address_id_doc,member.birthday,
        member.position,member.office_name,member.department_w
        FROM member
        INNER JOIN emp_function ON member.emp_function_id=emp_function.emp_function_id
        INNER JOIN emp_owner ON emp_owner.emp_owner_id=member.emp_owner_id
        INNER JOIN emp_contract ON emp_contract.emp_contract_id=member.emp_contract_id
        WHERE member.persion_id={pid}
        '''
        data = pd.read_sql_query(query, con=engine)
        data = data.squeeze().to_dict()
        data['document_addr'] = data.pop('address_id_doc')
        mem_id = data['mem_id']
        data['birthday'] = data['birthday'].isoformat()
        work_office = {}
        work_office['office_position'] = data.pop('position')
        work_office['office_name'] = data.pop('office_name')
        work_office['office_department'] = data.pop('department_w')
        work_office['function'] = data.pop('function_name')
        work_office['employer'] = data.pop('emp_owner_name')
        work_office['contract'] = data.pop('contract_name')
        query = f'''
        SELECT add_id,add1,moo,soi,road,zipcode,province.PROVINCE_NAME,amphur.AMPHUR_NAME,district.DISTRICT_NAME,updt
        FROM member_add
        INNER JOIN province ON province.PROVINCE_ID=member_add.PROVINCE_ID
        INNER JOIN amphur ON amphur.AMPHUR_ID=member_add.AMPHUR_ID
        INNER JOIN district ON district.DISTRICT_ID=member_add.DISTRICT_ID
        WHERE mem_id={mem_id}
        '''
        data['office'] = work_office

        addr = pd.read_sql_query(query, con=engine)
        for idx, row in addr.iterrows():
            dict_ = row.to_dict()
            dict_['updt'] = row['updt'].isoformat() if row['updt'] else None
            if dict_['add_id'] == 2:
                work_office['office_addr'] = dict_
            elif dict_['add_id'] == 1:
                data['current_addr'] = dict_
            elif dict_['add_id'] == 3:
                data['home_addr'] = dict_

        query = f'''
            SELECT lic_mem.lic_exp_date, cpd_work.w_bdate, cpd_work.cpd_score FROM cpd_work INNER JOIN member ON member.mem_id=cpd_work.mem_id
            INNER JOIN lic_mem ON lic_mem.mem_id=member.mem_id
            WHERE lic_id={mem_id} AND cpd_work.w_bdate BETWEEN lic_mem.lic_b_date AND lic_mem.lic_exp_date
            '''
        valid_score = pd.read_sql_query(query, con=engine).cpd_score.sum()
        query = f'''
            SELECT lic_mem.lic_exp_date, cpd_work.w_bdate, cpd_work.cpd_score FROM cpd_work INNER JOIN member ON member.mem_id=cpd_work.mem_id
            INNER JOIN lic_mem ON lic_mem.mem_id=member.mem_id
            WHERE lic_id={mem_id} 
            '''
        total_score = pd.read_sql_query(query, con=engine).cpd_score.sum()

        data['cmte_score'] = {'total': total_score, 'valid': valid_score}
        return jsonify({'data': data})
