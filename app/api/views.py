import datetime
import arrow
import os

import pandas as pd
from http import HTTPStatus

import requests
from flask import jsonify, request
from flask_jwt_extended import (create_access_token,
                                jwt_required,
                                get_jwt_identity,
                                create_refresh_token)
from flask_restful import Resource
from sqlalchemy import create_engine
from werkzeug.security import check_password_hash

from app import db
from app.members.models import Member, License
from app.cmte.models import CMTEFeePaymentRecord

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


class CMTEFeePaymentResource(Resource):
    @jwt_required()
    def get(self, lic_no):
        """
        This endpoint returns active CMTE fee payment.
        ---
        parameters:
            -   lic_no: license no.
                in: path
                type: string
                required: true
        responses:
            200:
                description: Active CMTE fee payment of the individual
                schema:
                    id: CMTEFeePaymentRecord
                    properties:
                        license_number:
                            type: string
                            description: license no.
                        start_date:
                            type: string
                            description: Start date
                        end_date:
                            type: string
                            description: End date
                        payment_datetime:
                            type: string
                            description: Payment date
        """
        license = License.query.filter_by(number=lic_no).first()
        active_payment_record = license.get_active_cmte_fee_payment()
        data = active_payment_record.to_dict() if active_payment_record else {}
        return jsonify(data=data)

    @jwt_required()
    def post(self, lic_no):
        """
        This endpoint posts CMTE fee payment data.
        ---
        consumes:
            -   application/json
        parameters:
            -   name: lic_no
                in: path
                type: string
                required: true
                description: License number
            -   name: payment_datetime
                in: body
                type: string
                required: true
                schema:
                    payment_datetime: string
                    properties:
                        payment_datetime:
                            type: string
                            description: Payment datetime in 'YYYY-MM-DD HH:MM:SS' format.

        responses:
            201:
                description: Active CMTE fee payment of the individual
                schema:
                    id: CMTEFeePaymentRecord
                    properties:
                        license_number:
                            type: string
                            description: license no.
                        start_date:
                            type: string
                            description: Start date
                        end_date:
                            type: string
                            description: End date
                        payment_datetime:
                            type: string
                            description: Payment date
        """
        payment_datetime = request.json.get('payment_datetime')
        print(payment_datetime)
        if payment_datetime:
            payment_datetime = arrow.get(payment_datetime, 'YYYY-MM-DD HH:mm:ss', tzinfo='Asia/Bangkok').datetime
        else:
            return {'message': 'Payment datetime required.'}, 400
        license = License.query.filter_by(number=lic_no).first()
        if license:
            record = CMTEFeePaymentRecord.query.filter_by(license=license,
                                                          start_date=license.start_date,
                                                          end_date=license.end_date).first()
            if not record:
                record = CMTEFeePaymentRecord(license_number=lic_no,
                                              payment_datetime=payment_datetime,
                                              start_date=license.start_date,
                                              end_date=license.end_date)
                db.session.add(record)
                db.session.commit()
                return {'data': record.to_dict()}, 201
            else:
                return {'message': 'Payment record already exists'}, 400
        else:
            return {'message': 'License not found.'}, 400


class CMTEScore(Resource):
    @jwt_required()
    def get(self, lic_id):
        """
        This endpoint returns CMTE scores.
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
        license = License.query.filter_by(number=lic_id).first()
        total_score = license.total_cmte_scores
        valid_score = license.valid_cmte_scores

        cmte_fee_payment_record = license.get_active_cmte_fee_payment()
        type_ = request.args.get('type', 'valid')
        if type_ == 'valid':
            score = valid_score
        elif type_ == 'total':
            score = total_score
        return jsonify({'data': {'scores': score,
                                 'type': type_,
                                 'active_cmte_payment_record': cmte_fee_payment_record.to_dict() if cmte_fee_payment_record else {},
                                 'datetime': datetime.datetime.now().isoformat()}})


BASE_URL = 'https://mtc.thaijobjob.com/api/user'
INET_API_TOKEN = os.environ.get('INET_API_TOKEN')


def check_exp_date_from_inet(license_id):
    try:
        response = requests.get(f'{BASE_URL}/GetdataBylicenseAndfirstnamelastname',
                                params={'search': license_id},
                                headers={'Authorization': 'Bearer {}'.format(INET_API_TOKEN)}, stream=True, timeout=99)
    except (requests.exceptions.ConnectionError, requests.exceptions.ConnectTimeout) as e:
        return
    else:
        try:
            data_ = response.json().get('results', [])
        except requests.exceptions.JSONDecodeError as e:
            return
        else:
            for rec in data_:
                return rec.get('end_date')


class MemberInfo(Resource):
    @jwt_required()
    def get(self, pin):
        """
        This end point returns personal information of a member with matching PIN.
        ---
        parameters:
            -   pin: Personal Identification Number
                in: path
                type: string
                required: true
        responses:
            200:
                description: Personal information of the member.
                schema:
                    id: Member
                    properties:
                        mem_id:
                            type: number
                            description: License ID
                        lic_b_date:
                            type: date
                            description: วันออกใบอนุญาต
                        lic_exp_date:
                            type: date
                            description: วันหมดอายุใบอนุญาต
                        lic_status_name:
                            type: string
                            description: สถานะใบอนุญาต
                        mem_id_text:
                            type: string
                            description: Member ID
                        birthday:
                            type: date
                            description: birthdate
                        title_id:
                            type: string
                            description: Thai title
                        fname:
                            type: string
                            description: Thai first name
                        lname:
                            type: string
                            description: Thai lastname
                        e_fname:
                            type: string
                            description: English first name
                        e_lname:
                            type: string
                            description: English lastname
                        e_title:
                            type: string
                            description: English title
                        cmte_score:
                            type: object
                            properties:
                                total:
                                    type: number
                                    description: คะแนนสะสมทั้งหมด
                                valid:
                                    type: number
                                    description: คะแนนสำหรับต่ออายุใบอนุญาตในรอบปัจจุบัน
                        active_cmte_payment:
                            type: object
                            properties:
                                end_date:
                                    type: string
                                    description: วันที่หมดอายุ mock up
                                start_date:
                                    type: string
                                    description: วันที่เริ่มต้น mock up
                        document_id:
                            type: integer
                            description: mailing address ที่อยู่สำหรับส่งเอกสาร, 1=current address, 2=work address, 3=home address
                        current_addr:
                            type: object
                            description: a current address ที่อยู่ปัจจุบัน
                            properties:
                                add_id:
                                    type: integer
                                    description: address ID, 1=current address, 2=work address, 3=home address
                                add1:
                                    type: string
                                    description: street address
                                zipcode:
                                    type: string
                                PROVINCE_NAME:
                                    type: string
                                AMPHUR_NAME:
                                    type: string
                                DISTRICT_NAME:
                                    type: string
                                moo:
                                    type: string
                                road:
                                    type: string
                                soi:
                                    type: string
                        mobilesms:
                            type: string
                            description: mobile phone
                        email_member:
                            type: string
                            description: email
                        mem_status:
                            type: string
                            description: สถานภาพสมาชิก
                        office:
                            type: object
                            properties:
                                contract:
                                    type: string
                                    description: ประเภทการจ้าง
                                employer:
                                    type: string
                                    description: ประเภทหน่วยงาน
                                function:
                                    type: string
                                    description: หน้าที่
                                office_name:
                                    type: string
                                    description: ชื่อสถานที่ทำงาน
                                office_department:
                                    type: string
                                    description: ชื่อหน่วยงาน/ภาควิชา
                                office_position:
                                    type: string
                                    description: ตำแหน่งงาน
                                office_addr:
                                    type: object
                                    properties:
                                        add_id:
                                            type: integer
                                            description: address ID, 1=current address, 2=work address, 3=home address
                                        add1:
                                            type: string
                                            description: street address
                                        zipcode:
                                            type: string
                                        PROVINCE_NAME:
                                            type: string
                                        AMPHUR_NAME:
                                            type: string
                                        DISTRICT_NAME:
                                            type: string
                                        moo:
                                            type: string
                                        road:
                                            type: string
                                        soi:
                                            type: string
        """
        engine = create_engine(f'mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}/{MYSQL_DATABASE}')
        engine.connect()
        query = f'''
        SELECT member.mem_id_txt,member.mem_id,member.title_id,member.fname,member.lname,member.e_title,member.e_fname,member.e_lname,
        member.address_id_doc,member.birthday,member.position,member.office_name,member.department_w,member.mobilesms,member.email_member,
        member.mem_status_id,member.emp_function_id,member.emp_owner_id,member.emp_contract_id
        FROM member WHERE member.persion_id='{pin}';
        '''
        data = pd.read_sql_query(query, con=engine)
        data = data.squeeze().to_dict()

        query = f'''
        SELECT lic_mem.lic_exp_date,lic_mem.lic_b_date FROM lic_mem
        INNER JOIN lic_status ON lic_mem.lic_status_id=lic_status.lic_status_id
        WHERE lic_mem.mem_id={data['mem_id']}
        '''
        lic_data = pd.read_sql_query(query, con=engine)
        lic_data = lic_data.squeeze().to_dict()
        data.update(lic_data)

        query = f'''
        SELECT status_name AS mem_status_name FROM mem_status WHERE {data['mem_status_id']}=mem_status.mem_status_id;
        '''

        mem_status_data = pd.read_sql_query(query, con=engine)
        data['mem_status'] = mem_status_data.squeeze()

        if data['emp_function_id']:
            query = f"""
            SELECT emp_function.function_name,emp_owner.emp_owner_name,emp_contract.contract_name
            FROM emp_function
            INNER JOIN emp_owner ON emp_owner.emp_owner_id={data['emp_owner_id']}
            INNER JOIN emp_contract ON emp_contract.emp_contract_id={data['emp_contract_id']}
            WHERE emp_function.emp_function_id={data['emp_function_id']}
            """
            emp_data = pd.read_sql_query(query, con=engine)
            data.update(emp_data.squeeze().to_dict())

        data['lic_b_date'] = data['lic_b_date'].isoformat() if data['lic_b_date'] else None
        data['lic_exp_date'] = data['lic_exp_date'].isoformat() if data['lic_exp_date'] else None
        data['document_addr'] = data.pop('address_id_doc', None) or ''
        data['birthday'] = data['birthday'].isoformat() if data['birthday'] else None

        work_office = {'office_position': data.pop('position', None) or '',
                       'office_name': data.pop('office_name', None) or '',
                       'office_department': data.pop('department_w', None) or '',
                       'function': data.pop('function_name', None) or '',
                       'employer': data.pop('emp_owner_name', None) or '',
                       'contract': data.pop('contract_name', None) or ''}
        mem_id = data['mem_id']
        data['office'] = work_office

        query = f'''
        SELECT add_id,add1,moo,soi,road,zipcode,province.PROVINCE_NAME,amphur.AMPHUR_NAME,district.DISTRICT_NAME,updt
        FROM member_add
        INNER JOIN province ON province.PROVINCE_ID=member_add.PROVINCE_ID
        INNER JOIN amphur ON amphur.AMPHUR_ID=member_add.AMPHUR_ID
        INNER JOIN district ON district.DISTRICT_ID=member_add.DISTRICT_ID
        WHERE mem_id={mem_id}
        '''

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

        member = Member.query.filter_by(pid=pin).first()
        cmte_fee_payment_record = member.license.get_active_cmte_fee_payment()
        total_score = member.license.total_cmte_scores
        valid_score = member.license.valid_cmte_scores
        data['active_cmte_payment'] = cmte_fee_payment_record.to_dict() if cmte_fee_payment_record else {}
        data['lic_b_date'] = member.license.start_date.strftime('%Y-%m-%d')
        data['lic_exp_date'] = member.license.end_date.strftime('%Y-%m-%d')

        data['cmte_score'] = {'total': total_score, 'valid': valid_score}
        return jsonify({'data': data})
