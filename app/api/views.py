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
from app.members.models import Member, License, MemberAddress
from app.cmte.models import CMTEFeePaymentRecord, CMTEEvent

MYSQL_HOST = os.environ.get('MYSQL_HOST')
MYSQL_USER = os.environ.get('MYSQL_USER')
MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD')
MYSQL_DATABASE = os.environ.get('MYSQL_DATABASE')


class Login(Resource):
    def post(self):
        """
        Authenticate a client and return JWT tokens.
        ---
        tags:
            -   Authentication
        summary: Authenticate user and issue access token.
        consumes:
            -   application/json
        produces:
            -   application/json
        parameters:
            -   in: body
                required: true
                schema:
                    type: object
                    required:
                        - client_id
                        - client_secret
                    properties:
                        client_id:
                            type: string
                        client_secret:
                            type: string
        responses:
            200:
                description: Token issued successfully
                schema:
                    type: object
                    required:
                        - access_token
                        - refresh_token
                    properties:
                        access_token:
                            type: string
                        refresh_token:
                            type: string
                examples:
                    application/json:
                        access_token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
                        refresh_token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
            400:
                description: Missing or invalid request body
            401:
                description: Unauthorized client ID or secret
            404:
                description: Client was not found
        """
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
        """
        Refresh an access token using a valid refresh token.
        ---
        tags:
            -   Authentication
        summary: Refresh access token
        responses:
            200:
                description: Token refreshed successfully
                schema:
                    type: object
                    required:
                        -   access_token
                    properties:
                        access_token:
                            type: string
                            description: New JWT access token
                examples:
                    application/json:
                        access_token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
            401:
                description: Invalid or expired refresh token
        """
        identity = get_jwt_identity()
        access_token = create_access_token(identity=identity)
        return jsonify(access_token=access_token)


class CMTEFeePaymentResource(Resource):
    @jwt_required()
    def get(self, lic_no):
        """
        Return the active CMTE fee payment record for a license.
        ---
        tags:
            -   CMTE
        parameters:
            -   name: lic_no
                in: path
                type: string
                required: true
                description: License number
        responses:
            200:
                description: Active CMTE fee payment of the individual
                schema:
                    type: object
                    properties:
                        data:
                            type: object
                            properties:
                                license_number:
                                    type: string
                                    description: License number
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
        Create a CMTE fee payment record for a license.
        ---
        tags:
            -   CMTE
        consumes:
            -   application/json
        parameters:
            -   name: lic_no
                in: path
                type: string
                required: true
                description: License number
            -   in: body
                required: true
                schema:
                    type: object
                    required:
                        - payment_datetime
                    properties:
                        payment_datetime:
                            type: string
                            description: Payment datetime in 'YYYY-MM-DD HH:MM:SS' format.

        responses:
            201:
                description: CMTE fee payment record created
                schema:
                    type: object
                    properties:
                        data:
                            type: object
                            properties:
                                license_number:
                                    type: string
                                    description: License number
                                start_date:
                                    type: string
                                    description: Start date
                                end_date:
                                    type: string
                                    description: End date
                                payment_datetime:
                                    type: string
                                    description: Payment date
            400:
                description: Payment datetime is missing, license was not found, or the payment record already exists
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
        Return CMTE scores for a license.
        ---
        tags:
            -   CMTE
        parameters:
            -   name: lic_id
                in: path
                type: string
                required: true
                description: License number
            -   name: type
                in: query
                type: string
                required: false
                enum:
                    - valid
                    - total
                default: valid
                description: Score type to return
        responses:
            200:
                description: Sum of the CMTE scores of the individual
                schema:
                    type: object
                    properties:
                        data:
                            type: object
                            properties:
                                scores:
                                    type: number
                                type:
                                    type: string
                                active_cmte_payment_record:
                                    type: object
                                datetime:
                                    type: string
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


class MemberPIDPhoneNumber(Resource):
    @jwt_required()
    def get(self, pid, phone=None):
        """
        Return member information filtered by personal ID and optionally by phone number.
        ---
        tags:
            -   Member
        parameters:
            -   name: pid
                in: path
                type: string
                required: true
                description: Personal Identification Number
            -   name: phone
                in: path
                type: string
                required: false
                description: Phone number
        responses:
            200:
                description: Member information
                schema:
                    type: object
                    properties:
                        data:
                            type: object
                            properties:
                                id:
                                    type: integer
                                pid:
                                    type: string
                                    description: หมายเลขบัตรประจำตัวประชาชน
                                firstname:
                                    type: string
                                    description: ชื่อ
                                lastname:
                                    type: string
                                    description: นามสกุล
                                phone:
                                    type: string
                                    description: หมายเลขโทรศัพท์
                                status:
                                    type: string
                                    description: สถานะสมาชิก
            400:
                description: Member status is not valid
            404:
                description: Member not found
        """

        if phone is not None:
            member = Member.query.filter_by(pid=pid, tel=phone).first()
        else:
            member = Member.query.filter_by(pid=pid).first()
        if member:
            status = member.status if member.status else 'ปกติ'
            if status == 'ปกติ':
                return {'data': {
                    'id': member.id,
                    'pid': member.pid,
                    'firstname': member.th_firstname,
                    'lastname': member.th_lastname,
                    'phone': member.tel,
                    'status': status,
                }}, 200
            else:
                return {'message': 'Member status is not valid.'}, 400
        else:
            return {'message': 'Member not found.'}, 404


class MemberPID(Resource):
    @jwt_required()
    def get(self, pid):
        """
        Return member and license information for a personal identification number.
        ---
        tags:
            -   Member
        parameters:
            -   name: pid
                in: path
                type: string
                required: true
                description: Personal Identification Number
        responses:
            200:
                description: License information
                schema:
                    type: object
                    properties:
                        data:
                            type: object
                            properties:
                                license:
                                    type: object
                                    properties:
                                        number:
                                            type: string
                                            description: หมายเลขใบอนุญาต (ท.น.)
                                        lic_b_date:
                                            type: string
                                            description: วันออกใบอนุญาต
                                        lic_exp_date:
                                            type: string
                                            description: วันหมดอายุใบอนุญาต
                                        lic_status_name:
                                            type: string
                                            description: สถานะใบอนุญาต
                                member:
                                    type: object
                                    properties:
                                        th_title:
                                            type: string
                                            description: คำนำหน้า
                                        th_firstname:
                                            type: string
                                            description: ชื่อภาษาไทย
                                        th_lastname:
                                            type: string
                                            description: นามสกุลภาษาไทย
                                        telephone:
                                            type: string
                                            description: หมายเลขโทรศัพท์
                                        status:
                                            type: string
                                            description: สถานะสมาชิก
            404:
                description: Member not found
        """
        member = Member.query.filter_by(pid=pid).first()
        if member:
            # cmte_fee_payment_record = member.license.get_active_cmte_fee_payment()
            # valid_score = member.license.valid_cmte_scores

            data = {
                'license': {
                    'number': member.license.number if member.license else "",
                    'lic_b_date': member.license.issue_date.strftime('%Y-%m-%d') if member.license else "",
                    'lic_status_name': member.license.status or 'ปกติ' if member.license else "",
                    'lic_exp_date': member.license.end_date.strftime('%Y-%m-%d') if member.license else "",
                },
                'member': {
                    'th_title': member.th_title,
                    'th_firstname': member.th_firstname,
                    'th_lastname': member.th_lastname,
                    'telephone': member.tel,
                    'status': member.status or 'ปกติ',
                },
            }
            if member.license:
                data['license'] = {
                    'number': member.license.number,
                    'lic_b_date': member.license.issue_date.strftime('%Y-%m-%d'),
                    'lic_status_name': member.license.status or 'ปกติ',
                    'lic_exp_date': member.license.end_date.strftime('%Y-%m-%d'),
                }
            else:
                data['license'] = {}
            return {'data': data}
        return {'message': 'Member not found.'}, 404


class MemberLicense(Resource):
    @jwt_required()
    def get(self, license_number):
        """
        Return member, license, and CMTE information for a license number.
        ---
        tags:
            -   Member
        parameters:
            -   name: license_number
                in: path
                type: string
                required: true
                description: License number
        responses:
            200:
                description: License information
                schema:
                    type: object
                    properties:
                        data:
                            type: object
                            properties:
                                license:
                                    type: object
                                    properties:
                                        number:
                                            type: string
                                            description: หมายเลขใบอนุญาต (ท.น.)
                                        lic_b_date:
                                            type: string
                                            description: วันออกใบอนุญาต
                                        lic_exp_date:
                                            type: string
                                            description: วันหมดอายุใบอนุญาต
                                        lic_status_name:
                                            type: string
                                            description: สถานะใบอนุญาต
                                member:
                                    type: object
                                    properties:
                                        th_title:
                                            type: string
                                            description: คำนำหน้า
                                        th_firstname:
                                            type: string
                                            description: ชื่อภาษาไทย
                                        th_lastname:
                                            type: string
                                            description: นามสกุลภาษาไทย
                                cmte:
                                    type: object
                                    properties:
                                        valid_score:
                                            type: number
                                            description: คะแนนสำหรับต่ออายุใบอนุญาตในรอบปัจจุบัน
                                        active_cmte_payment:
                                            type: object
                                            properties:
                                                end_date:
                                                    type: string
                                                start_date:
                                                    type: string
            404:
                description: License or member not found
        """
        license = License.query.filter_by(number=license_number).first()
        member = Member.query.get(license.member_id)
        if member:
            cmte_fee_payment_record = member.license.get_active_cmte_fee_payment()
            valid_score = member.license.valid_cmte_scores
            data = {
                'license': {
                    'number': license.number,
                    'lic_b_date': license.issue_date.strftime('%Y-%m-%d'),
                    'lic_status_name': license.status or 'ปกติ',
                    'lic_exp_date': license.end_date.strftime('%Y-%m-%d'),
                },
                'member': {
                    'th_title': license.member.th_title,
                    'th_firstname': license.member.th_firstname,
                    'th_lastname': license.member.th_lastname,
                },
                'cmte': {
                    'active_cmte_payment': cmte_fee_payment_record.to_dict() if cmte_fee_payment_record else {},
                    'valid_score': valid_score,
                }
            }
            return jsonify(data=data)
        return jsonify(data=None), 404


class MemberAddressResource(Resource):
    ADDRESS_TYPE_MAP = {
        'mailing': 1,
        'work': 2,
        'home': 3,
    }
    ADDRESS_TYPE_LABELS = {
        1: 'mailing',
        2: 'work',
        3: 'home',
    }
    ADDRESS_FIELD_ALIASES = {
        'street_number': ('street_number', 'add1'),
        'alley': ('alley', 'soi'),
        'street': ('street', 'road'),
        'village': ('village', 'moo'),
        'district': ('district', 'DISTRICT_NAME'),
        'city': ('city', 'AMPHUR_NAME'),
        'province': ('province', 'PROVINCE_NAME'),
        'zipcode': ('zipcode',),
    }

    @classmethod
    def _parse_address_type(cls, raw_value):
        if raw_value is None:
            return None
        if isinstance(raw_value, int):
            return raw_value if raw_value in cls.ADDRESS_TYPE_LABELS else None
        return cls.ADDRESS_TYPE_MAP.get(str(raw_value).strip().lower())

    @classmethod
    def _serialize_address(cls, address):
        return {
            'id': address.id,
            'address_type': cls.ADDRESS_TYPE_LABELS.get(address.address_type, address.address_type),
            'street_number': address.street_number,
            'alley': address.alley,
            'street': address.street,
            'village': address.village,
            'district': address.district,
            'city': address.city,
            'province': address.province,
            'zipcode': str(address.zipcode) if address.zipcode is not None else None,
            'updated_at': address.updated_at.isoformat() if address.updated_at else None,
        }

    @jwt_required()
    def put(self, pin):
        """
        Create or update a member mailing, work, or home address.
        ---
        tags:
            -   Member
        summary: Update member address information
        consumes:
            -   application/json
        produces:
            -   application/json
        parameters:
            -   name: pin
                in: path
                type: string
                required: true
                description: Personal Identification Number
            -   in: body
                required: true
                schema:
                    type: object
                    required:
                        - address_type
                    properties:
                        address_type:
                            type: string
                            description: Address type to create or update
                            enum: [mailing, work, home]
                        address:
                            type: object
                            description: Address fields. The endpoint also accepts these fields at the top level.
                            properties:
                                street_number:
                                    type: string
                                    description: House number or primary street line
                                alley:
                                    type: string
                                    description: Alley or soi
                                street:
                                    type: string
                                    description: Street or road name
                                village:
                                    type: string
                                    description: Village or moo
                                district:
                                    type: string
                                    description: District / subdistrict
                                city:
                                    type: string
                                    description: City / amphur
                                province:
                                    type: string
                                    description: Province
                                zipcode:
                                    type: string
                                    description: Postal code
                examples:
                    application/json:
                        address_type: work
                        address:
                            street_number: 12/34
                            alley: Sukhumvit 10
                            street: Sukhumvit
                            village: Village 5
                            district: Khlong Toei
                            city: Bangkok
                            province: Bangkok
                            zipcode: "10110"
        responses:
            200:
                description: Address updated successfully
                schema:
                    type: object
                    properties:
                        data:
                            type: object
                            properties:
                                id:
                                    type: integer
                                address_type:
                                    type: string
                                    enum: [mailing, work, home]
                                street_number:
                                    type: string
                                alley:
                                    type: string
                                street:
                                    type: string
                                village:
                                    type: string
                                district:
                                    type: string
                                city:
                                    type: string
                                province:
                                    type: string
                                zipcode:
                                    type: string
                                updated_at:
                                    type: string
                                    description: ISO 8601 timestamp
            201:
                description: Address created successfully
                schema:
                    type: object
                    properties:
                        data:
                            type: object
                            properties:
                                id:
                                    type: integer
                                address_type:
                                    type: string
                                    enum: [mailing, work, home]
                                street_number:
                                    type: string
                                alley:
                                    type: string
                                street:
                                    type: string
                                village:
                                    type: string
                                district:
                                    type: string
                                city:
                                    type: string
                                province:
                                    type: string
                                zipcode:
                                    type: string
                                updated_at:
                                    type: string
                                    description: ISO 8601 timestamp
            400:
                description: Invalid request payload
            404:
                description: Member not found
        """
        member = Member.query.filter_by(pid=pin).first()
        if not member:
            return {'message': 'Member not found.'}, HTTPStatus.NOT_FOUND

        payload = request.get_json(silent=True) or {}
        if not payload:
            return {'message': 'JSON body required.'}, HTTPStatus.BAD_REQUEST

        address_payload = payload.get('address') if isinstance(payload.get('address'), dict) else payload
        address_type = self._parse_address_type(payload.get('address_type') or address_payload.get('address_type'))
        if address_type is None:
            return {'message': 'address_type must be one of "mailing", "work", or "home".'}, HTTPStatus.BAD_REQUEST

        address = MemberAddress.query.filter_by(member=member, address_type=address_type).first()
        created = address is None
        if created:
            address = MemberAddress(member=member, address_type=address_type)
            db.session.add(address)

        updated_fields = 0
        for field_name, aliases in self.ADDRESS_FIELD_ALIASES.items():
            for alias in aliases:
                if alias not in address_payload:
                    continue

                value = address_payload.get(alias)
                if field_name == 'zipcode':
                    if value in (None, ''):
                        normalized_value = None
                    else:
                        try:
                            normalized_value = int(str(value).strip())
                        except (TypeError, ValueError):
                            return {'message': 'zipcode must be numeric.'}, HTTPStatus.BAD_REQUEST
                else:
                    normalized_value = value.strip() if isinstance(value, str) else value
                    if normalized_value == '':
                        normalized_value = None

                setattr(address, field_name, normalized_value)
                updated_fields += 1
                break

        if updated_fields == 0:
            return {'message': 'No address fields provided.'}, HTTPStatus.BAD_REQUEST

            db.session.commit()
            status = HTTPStatus.CREATED if created else HTTPStatus.OK
        return {'data': self._serialize_address(address)}, status


class MemberInfo(Resource):
    # TODO: Add an endpoint for adding new member
    @jwt_required()
    def get(self, pin):
        """
        This end point returns personal information of a member with matching PIN.
        ---
        tags:
            -   Member
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
                        lic_number:
                            type: string
                            description: หมายเลขใบอนุญาต ท.น.
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
        member = Member.query.filter_by(pid=pin).first()
        if not member:
            return {'message': 'Member not found.'}, 404

        engine = create_engine(f'mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}/{MYSQL_DATABASE}')
        engine.connect()
        query = f'''
        SELECT member.mem_id_txt,member.mem_id,member.title_id,member.fname,member.lname,member.e_title,member.e_fname,member.e_lname,
        member.address_id_doc,member.birthday,member.position,member.office_name,member.department_w,member.mobilesms,member.email_member,
        member.mem_status_id,member.emp_function_id,member.emp_owner_id,member.emp_contract_id
        FROM member WHERE member.persion_id='{pin}';
        '''
        try:
            data = pd.read_sql_query(query, con=engine)
        except:
            data = {}
        else:
            data = data.squeeze().to_dict()

        data['mem_status'] = member.status if member else None

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

        data['lic_b_date'] = member.license.start_date.isoformat()
        data['lic_number'] = member.license.number
        data['lic_exp_date'] = member.license.end_date.isoformat()
        data['document_addr'] = data.pop('address_id_doc', None) or ''
        data['birthday'] = member.dob.isoformat() if member.dob else None

        work_office = {'office_position': data.pop('position', None) or '',
                       'office_name': data.pop('office_name', None) or '',
                       'office_department': data.pop('department_w', None) or '',
                       'function': data.pop('function_name', None) or '',
                       'employer': data.pop('emp_owner_name', None) or '',
                       'contract': data.pop('contract_name', None) or ''}
        mem_id = data.get('mem_id', None)
        data['office'] = work_office

        if mem_id:
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
        else:
            data['current_addr'] = {}
            data['home_addr'] = {}
            data['office_addr'] = {}

        cmte_fee_payment_record = member.license.get_active_cmte_fee_payment()
        total_score = member.license.total_cmte_scores
        valid_score = member.license.valid_cmte_scores
        data['active_cmte_payment'] = cmte_fee_payment_record.to_dict() if cmte_fee_payment_record else {}
        data['lic_b_date'] = member.license.start_date.strftime('%Y-%m-%d')
        data['lic_exp_date'] = member.license.end_date.strftime('%Y-%m-%d')

        data['cmte_score'] = {'total': float(total_score), 'valid': float(valid_score)}
        return {'data': data}


class CMTEEventResource(Resource):
    @jwt_required()
    def get(self):
        """
        This endpoint returns upcoming CMTE events.
        ---
        responses:
            200:
                description: List of all upcoming CMTE events
                schema:
                    id: CMTEEvent
                    properties:
                        id:
                            type: number
                            description: event ID
                        title:
                            type: string
                            description: Event title
                        venue:
                            type: string
                            description: Event venue
                        score:
                            type: number
                            description: CMTE score
                        website:
                            type: string
                            description: Website URL
                        organizer:
                            type: string
                            description: Organizer
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
        query = CMTEEvent.query.filter(CMTEEvent.start_date >= datetime.datetime.today())
        upcoming_events = []
        for event in query:
            upcoming_events.append(event.to_dict())
        return jsonify({'data': upcoming_events})
