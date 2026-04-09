import os
import datetime
import arrow
from http import HTTPStatus
from dateutil.relativedelta import relativedelta

import requests
from flask import jsonify, request
from flask_jwt_extended import (create_access_token,
                                jwt_required,
                                get_jwt_identity,
                                create_refresh_token)
from flask_restful import Resource
from werkzeug.security import check_password_hash

from app import db
from app.members.models import Member, License, MemberAddress, LicenseRenewal, MemberEducationRecord
from app.cmte.models import CMTEFeePaymentRecord, CMTEEvent


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


class MemberLicenseRegistrationResource(Resource):
    REQUIRED_FIELDS = ('member_id_txt', 'member_idpeople', 'member_license', 'groupdate')
    IGNORED_FIELDS = {
        'member_name',
        'member_midname',
        'member_surname',
        'group_id',
        'prefix',
    }

    @staticmethod
    def _normalize_value(value):
        if isinstance(value, str):
            value = value.strip()
            if value == '':
                return None
        return value

    @staticmethod
    def _parse_group_date(raw_value):
        try:
            return datetime.datetime.strptime(raw_value, '%Y-%m-%d %H:%M:%S').date()
        except (TypeError, ValueError):
            raise ValueError('groupdate must be in YYYY-MM-DD HH:MM:SS format.')

    @staticmethod
    def _apply_license_registration(member_id, license_number, group_date, status='ปกติ'):
        latest_license = License.query.filter_by(member_id=member_id) \
            .order_by(License.end_date.desc()).first()
        end_date = group_date + relativedelta(years=5, days=-1) if group_date else None

        if latest_license and group_date:
            renewal = LicenseRenewal.query.filter_by(
                license=latest_license,
                start_date=group_date,
            ).first()
            if not renewal:
                renewal = LicenseRenewal(license=latest_license)
            renewal.issue_date = group_date
            renewal.start_date = group_date
            renewal.end_date = end_date
            db.session.add(renewal)

            if latest_license.end_date and group_date > latest_license.end_date:
                latest_license.number = license_number
                latest_license.issue_date = group_date
                latest_license.start_date = group_date
                latest_license.end_date = end_date
                latest_license.status = status
                db.session.add(latest_license)
            return latest_license

        if not latest_license:
            latest_license = License(member_id=member_id, number=license_number)

        latest_license.number = license_number
        latest_license.issue_date = group_date
        latest_license.start_date = group_date
        latest_license.end_date = end_date
        latest_license.status = status
        db.session.add(latest_license)
        return latest_license

    @staticmethod
    def _serialize_license(license):
        return {
            'id': license.id,
            'number': license.number,
            'member_id': license.member_id,
            'issue_date': license.issue_date.isoformat() if license.issue_date else None,
            'start_date': license.start_date.isoformat() if license.start_date else None,
            'end_date': license.end_date.isoformat() if license.end_date else None,
            'status': license.status,
        }

    @jwt_required()
    def post(self):
        """
        Bulk create or update member licenses from a registration payload.
        ---
        tags:
            -   Member
        consumes:
            -   application/json
        produces:
            -   application/json
        responses:
            200:
                description: Licenses processed successfully
            400:
                description: Invalid request payload
        """
        payload = request.get_json(silent=True) or {}
        users = payload.get('user')
        if not isinstance(users, list) or not users:
            return {'message': 'user must be a non-empty list.'}, HTTPStatus.BAD_REQUEST

        processed_licenses = []
        skipped_licenses = []

        for index, user in enumerate(users):
            if not isinstance(user, dict):
                return {'message': f'user[{index}] must be an object.'}, HTTPStatus.BAD_REQUEST

            normalized_user = {
                field_name: self._normalize_value(user.get(field_name))
                for field_name in ('member_id_txt', 'member_idpeople', 'member_license', 'groupdate', 'status')
            }

            missing_fields = [
                field_name for field_name in self.REQUIRED_FIELDS
                if normalized_user.get(field_name) is None
            ]
            if missing_fields:
                return {
                    'message': f'user[{index}] is missing required fields: {", ".join(missing_fields)}.'
                }, HTTPStatus.BAD_REQUEST

            incoming_status = (normalized_user.get('status') or '').lower()
            if incoming_status and incoming_status != 'approve':
                skipped_licenses.append({
                    'index': index,
                    'member_id_txt': normalized_user['member_id_txt'],
                    'member_idpeople': normalized_user['member_idpeople'],
                    'member_license': normalized_user['member_license'],
                    'reason': 'status is not approve.',
                })
                continue

            try:
                group_date = self._parse_group_date(normalized_user['groupdate'])
            except ValueError as exc:
                return {'message': f'user[{index}] {exc}'}, HTTPStatus.BAD_REQUEST

            member = Member.query.filter_by(pid=normalized_user['member_idpeople']).first()
            if member is None:
                member = Member.query.filter_by(number=normalized_user['member_id_txt']).first()

            if member is None:
                skipped_licenses.append({
                    'index': index,
                    'member_id_txt': normalized_user['member_id_txt'],
                    'member_idpeople': normalized_user['member_idpeople'],
                    'member_license': normalized_user['member_license'],
                    'reason': 'member not found.',
                })
                continue

            license = self._apply_license_registration(
                member_id=member.id,
                license_number=normalized_user['member_license'],
                group_date=group_date,
                status='ปกติ',
            )
            processed_licenses.append({
                'index': index,
                'member': {
                    'id': member.id,
                    'number': member.number,
                    'pid': member.pid,
                },
                'license': self._serialize_license(license),
                'ignored_fields': sorted(field for field in user.keys() if field in self.IGNORED_FIELDS),
            })

        if not processed_licenses and skipped_licenses:
            return {
                'message': 'No licenses were processed.',
                'processed_count': 0,
                'skipped_count': len(skipped_licenses),
                'skipped': skipped_licenses,
            }, HTTPStatus.OK

        db.session.commit()

        return {
            'message': 'Member license registration processed.',
            'processed_count': len(processed_licenses),
            'skipped_count': len(skipped_licenses),
            'data': processed_licenses,
            'skipped': skipped_licenses,
        }, HTTPStatus.OK


class MemberRegistrationResource(Resource):
    BEGIN_DATE_REQUIRED_FIELDS = ('member_id_txt', 'member_idpeople', 'groupdate')
    BEGIN_DATE_IGNORED_FIELDS = {
        'prefix',
        'member_name',
        'member_midname',
        'member_surname',
        'group_id',
    }

    @classmethod
    def _normalize_value(cls, value):
        if isinstance(value, str):
            value = value.strip()
            if value == '':
                return None
        return value

    @classmethod
    def _serialize_member(cls, member):
        return {
            'id': member.id,
            'number': member.number,
            'pid': member.pid,
            'th_title': member.th_title,
            'th_firstname': member.th_firstname,
            'th_lastname': member.th_lastname,
            'status': member.status,
            'begin_date': member.begin_date.isoformat() if member.begin_date else None,
        }

    @staticmethod
    def _parse_begin_date(raw_value):
        try:
            return datetime.datetime.strptime(raw_value, '%Y-%m-%d %H:%M:%S').date()
        except (TypeError, ValueError):
            raise ValueError('groupdate must be in YYYY-MM-DD HH:MM:SS format.')

    @jwt_required()
    def put(self):
        """
        Bulk update member begin_date from a member payload.
        ---
        tags:
            -   Member
        consumes:
            -   application/json
        produces:
            -   application/json
        responses:
            200:
                description: Members updated successfully
            400:
                description: Invalid request payload
        """
        payload = request.get_json(silent=True) or {}
        users = payload.get('user')
        if not isinstance(users, list) or not users:
            return {'message': 'user must be a non-empty list.'}, HTTPStatus.BAD_REQUEST

        updated_members = []
        skipped_members = []

        for index, user in enumerate(users):
            if not isinstance(user, dict):
                return {'message': f'user[{index}] must be an object.'}, HTTPStatus.BAD_REQUEST

            normalized_user = {
                field_name: self._normalize_value(user.get(field_name))
                for field_name in ('member_id_txt', 'member_idpeople', 'groupdate', 'status')
            }

            missing_fields = [
                field_name for field_name in self.BEGIN_DATE_REQUIRED_FIELDS
                if normalized_user.get(field_name) is None
            ]
            if missing_fields:
                return {
                    'message': f'user[{index}] is missing required fields: {", ".join(missing_fields)}.'
                }, HTTPStatus.BAD_REQUEST

            incoming_status = (normalized_user.get('status') or '').lower()
            if incoming_status and incoming_status != 'approve':
                skipped_members.append({
                    'index': index,
                    'member_id_txt': normalized_user['member_id_txt'],
                    'member_idpeople': normalized_user['member_idpeople'],
                    'reason': 'status is not approve.',
                })
                continue

            try:
                begin_date = self._parse_begin_date(normalized_user['groupdate'])
            except ValueError as exc:
                return {'message': f'user[{index}] {exc}'}, HTTPStatus.BAD_REQUEST

            member = Member.query.filter_by(pid=normalized_user['member_idpeople']).first()
            if member is None:
                member = Member.query.filter_by(number=normalized_user['member_id_txt']).first()

            if member is None:
                skipped_members.append({
                    'index': index,
                    'member_id_txt': normalized_user['member_id_txt'],
                    'member_idpeople': normalized_user['member_idpeople'],
                    'reason': 'member not found.',
                })
                continue

            member.begin_date = begin_date
            db.session.add(member)
            updated_members.append({
                'index': index,
                'member': self._serialize_member(member),
                'ignored_fields': sorted(field for field in user.keys() if field in self.BEGIN_DATE_IGNORED_FIELDS),
            })

        if not updated_members and skipped_members:
            return {
                'message': 'No members were updated.',
                'updated_count': 0,
                'skipped_count': len(skipped_members),
                'skipped': skipped_members,
            }, HTTPStatus.OK

        db.session.commit()

        return {
            'message': 'Member begin_date update processed.',
            'updated_count': len(updated_members),
            'skipped_count': len(skipped_members),
            'data': updated_members,
            'skipped': skipped_members,
        }, HTTPStatus.OK


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
        'building': ('building',),
        'alley': ('alley', 'soi'),
        'street': ('street', 'road'),
        'village': ('village', 'moo'),
        'district': ('district', 'DISTRICT_NAME'),
        'city': ('city', 'AMPHUR_NAME'),
        'province': ('province', 'PROVINCE_NAME'),
        'zipcode': ('zipcode',),
    }
    BULK_ADDRESS_TYPE_MAP = {
        'now': 1,
        'contact': 2,
        'regis': 3,
        'send_document': 1,
    }
    BULK_ADDRESS_FIELD_MAP = {
        'street_number': 'no',
        'building': 'building',
        'village': 'moo',
        'street': 'road',
        'alley': 'soi',
        'province': 'province',
        'city': 'amphures',
        'district': 'tambons',
        'zipcode': 'zipcode',
    }
    BULK_IGNORED_FIELDS = {
        'idcardnumber',
        'address_id',
        'member_id',
        'check_address_now',
        'send_documents_address',
    }

    @staticmethod
    def _resolve_member(pin, payload):
        member_pin = pin
        if member_pin is None and isinstance(payload, dict):
            member_pin = payload.get('idcardnumber')
        if member_pin is None:
            return None
        return Member.query.filter_by(pid=str(member_pin).strip()).first()

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
            'building': address.building,
            'alley': address.alley,
            'street': address.street,
            'village': address.village,
            'district': address.district,
            'city': address.city,
            'province': address.province,
            'zipcode': str(address.zipcode) if address.zipcode is not None else None,
            'updated_at': address.updated_at.isoformat() if address.updated_at else None,
        }

    @staticmethod
    def _normalize_address_value(field_name, value):
        if field_name == 'zipcode':
            if value in (None, ''):
                return None
            try:
                return int(str(value).strip())
            except (TypeError, ValueError):
                raise ValueError('zipcode must be numeric.')

        normalized_value = value.strip() if isinstance(value, str) else value
        if normalized_value == '':
            return None
        return normalized_value

    @classmethod
    def _update_address_from_payload(cls, address, payload):
        updated_fields = 0
        for field_name, aliases in cls.ADDRESS_FIELD_ALIASES.items():
            for alias in aliases:
                if alias not in payload:
                    continue

                normalized_value = cls._normalize_address_value(field_name, payload.get(alias))
                setattr(address, field_name, normalized_value)
                updated_fields += 1
                break
        return updated_fields

    @classmethod
    def _upsert_member_address(cls, member, address_type, payload):
        address = MemberAddress.query.filter_by(member=member, address_type=address_type).first()
        created = address is None
        if created:
            address = MemberAddress(member=member, address_type=address_type)
            db.session.add(address)

        updated_fields = cls._update_address_from_payload(address, payload)
        return address, created, updated_fields

    @classmethod
    def _extract_bulk_address_payloads(cls, payload):
        address_entries = payload.get('address')
        if not isinstance(address_entries, list) or not address_entries:
            return None, {'message': 'address must be a non-empty list.'}, HTTPStatus.BAD_REQUEST

        address_data = address_entries[0]
        if not isinstance(address_data, dict):
            return None, {'message': 'address items must be objects.'}, HTTPStatus.BAD_REQUEST

        bulk_payloads = {}
        ignored_fields = []

        for raw_field, value in address_data.items():
            matched = False
            for suffix, address_type in cls.BULK_ADDRESS_TYPE_MAP.items():
                suffix_token = f'_{suffix}'
                if not raw_field.endswith(suffix_token):
                    continue

                base_name = raw_field[:-len(suffix_token)]
                target_field = cls.BULK_ADDRESS_FIELD_MAP.get(base_name)
                if target_field is None:
                    ignored_fields.append(raw_field)
                    matched = True
                    break

                bulk_payloads.setdefault(address_type, {})[target_field] = value
                matched = True
                break

            if matched:
                continue

            if raw_field in cls.BULK_IGNORED_FIELDS:
                ignored_fields.append(raw_field)
            else:
                ignored_fields.append(raw_field)

        return {
            'bulk_payloads': bulk_payloads,
            'ignored_fields': sorted(set(ignored_fields)),
        }, None, None

    @jwt_required()
    def put(self, pin=None):
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
        payload = request.get_json(silent=True) or {}
        if not payload:
            return {'message': 'JSON body required.'}, HTTPStatus.BAD_REQUEST

        member = self._resolve_member(pin, payload)
        if not member:
            return {'message': 'Member not found.'}, HTTPStatus.NOT_FOUND

        if isinstance(payload.get('address'), list):
            parsed_payload, error_body, error_status = self._extract_bulk_address_payloads(payload)
            if error_body:
                return error_body, error_status

            bulk_payloads = parsed_payload['bulk_payloads']
            ignored_fields = parsed_payload['ignored_fields']
            if not bulk_payloads:
                return {'message': 'No supported address fields provided.'}, HTTPStatus.BAD_REQUEST

            results = []
            created_any = False
            try:
                for address_type, address_payload in bulk_payloads.items():
                    address, created, updated_fields = self._upsert_member_address(member, address_type, address_payload)
                    if updated_fields == 0:
                        continue
                    results.append(self._serialize_address(address))
                    created_any = created_any or created
            except ValueError as exc:
                return {'message': str(exc)}, HTTPStatus.BAD_REQUEST

            if not results:
                return {'message': 'No supported address fields provided.'}, HTTPStatus.BAD_REQUEST

            db.session.commit()
            status = HTTPStatus.CREATED if created_any else HTTPStatus.OK
            return {
                'data': results,
                'ignored_fields': ignored_fields,
            }, status

        flat_bulk_payload, _, _ = self._extract_bulk_address_payloads({'address': [payload]})
        bulk_payloads = flat_bulk_payload['bulk_payloads']
        ignored_fields = flat_bulk_payload['ignored_fields']
        if bulk_payloads:
            results = []
            created_any = False
            try:
                for address_type, address_payload in bulk_payloads.items():
                    address, created, updated_fields = self._upsert_member_address(member, address_type, address_payload)
                    if updated_fields == 0:
                        continue
                    results.append(self._serialize_address(address))
                    created_any = created_any or created
            except ValueError as exc:
                return {'message': str(exc)}, HTTPStatus.BAD_REQUEST

            if not results:
                return {'message': 'No supported address fields provided.'}, HTTPStatus.BAD_REQUEST

            db.session.commit()
            status = HTTPStatus.CREATED if created_any else HTTPStatus.OK
            return {
                'data': results,
                'ignored_fields': ignored_fields,
            }, status

        address_payload = payload.get('address') if isinstance(payload.get('address'), dict) else payload
        address_type = self._parse_address_type(payload.get('address_type') or address_payload.get('address_type'))
        if address_type is None:
            return {'message': 'address_type must be one of "mailing", "work", or "home".'}, HTTPStatus.BAD_REQUEST

        try:
            address, created, updated_fields = self._upsert_member_address(member, address_type, address_payload)
        except ValueError as exc:
            return {'message': str(exc)}, HTTPStatus.BAD_REQUEST

        if updated_fields == 0:
            return {'message': 'No address fields provided.'}, HTTPStatus.BAD_REQUEST

        db.session.commit()
        status = HTTPStatus.CREATED if created else HTTPStatus.OK
        return {'data': self._serialize_address(address)}, status


class MemberEducationResource(Resource):
    EDUCATION_FIELD_MAP = {
        'educational_degree': 'degree_name',
        'educational_name': 'institution',
        'graduate_year': 'graduate_year',
    }
    IGNORED_FIELDS = {'member_id', 'id'}
    DEFAULT_DEGREE_LEVEL = 'ปริญญาตรี'

    @staticmethod
    def _serialize_education(record):
        return {
            'id': record.id,
            'education_id': record.education_id,
            'member_id': record.member_id,
            'degree_level': record.degree_level,
            'degree_name': record.degree_name,
            'institution': record.institution,
            'graduate_year': record.graduate_year,
        }

    @staticmethod
    def _normalize_value(value):
        if isinstance(value, str):
            value = value.strip()
            if value == '':
                return None
        return value

    @classmethod
    def _normalize_graduate_year(cls, value):
        value = cls._normalize_value(value)
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            raise ValueError('graduate_year must be numeric.')

    @jwt_required()
    def put(self):
        """
        Create or update member education records by idcardnumber.
        ---
        tags:
            -   Member
        consumes:
            -   application/json
        produces:
            -   application/json
        responses:
            200:
                description: Education records processed successfully
            400:
                description: Invalid request payload
            404:
                description: Member not found
        """
        payload = request.get_json(silent=True) or {}
        idcardnumber = self._normalize_value(payload.get('idcardnumber'))
        education_items = payload.get('education')

        if idcardnumber is None:
            return {'message': 'idcardnumber is required.'}, HTTPStatus.BAD_REQUEST
        if not isinstance(education_items, list) or not education_items:
            return {'message': 'education must be a non-empty list.'}, HTTPStatus.BAD_REQUEST

        member = Member.query.filter_by(pid=idcardnumber).first()
        if not member:
            return {'message': 'Member not found.'}, HTTPStatus.NOT_FOUND

        processed_records = []

        for index, item in enumerate(education_items):
            if not isinstance(item, dict):
                return {'message': f'education[{index}] must be an object.'}, HTTPStatus.BAD_REQUEST

            education_id = self._normalize_value(item.get('education_id'))
            if education_id is not None:
                record = MemberEducationRecord.query.filter_by(education_id=education_id).first()
                if record is not None and record.member_id != member.id:
                    return {
                        'message': f'education[{index}].education_id already belongs to another member.'
                    }, HTTPStatus.BAD_REQUEST
                if record is None:
                    record = MemberEducationRecord(member=member, education_id=education_id)
                    db.session.add(record)
                    created = True
                else:
                    created = False
            else:
                record = MemberEducationRecord(member=member)
                db.session.add(record)
                created = True

            degree_name = self._normalize_value(item.get('educational_degree'))
            institution = self._normalize_value(item.get('educational_name'))
            if degree_name is None or institution is None:
                return {
                    'message': f'education[{index}] requires educational_degree and educational_name.'
                }, HTTPStatus.BAD_REQUEST

            record.degree_level = self.DEFAULT_DEGREE_LEVEL
            record.education_id = education_id
            record.institution = institution
            record.degree_name = degree_name
            try:
                record.graduate_year = self._normalize_graduate_year(item.get('graduate_year'))
            except ValueError as exc:
                return {'message': f'education[{index}] {exc}'}, HTTPStatus.BAD_REQUEST

            db.session.add(record)
            processed_records.append({
                'index': index,
                'created': created,
                'education': self._serialize_education(record),
                'ignored_fields': sorted(field for field in item.keys() if field in self.IGNORED_FIELDS),
            })

        db.session.commit()

        return {
            'message': 'Member education records processed.',
            'processed_count': len(processed_records),
            'data': processed_records,
        }, HTTPStatus.OK


class MemberInfo(Resource):
    PROFILE_FIELD_MAP = {
        'prefix': 'th_title',
        'prefixEN': 'en_title',
        'firstnameTH': 'th_firstname',
        'lastnameTH': 'th_lastname',
        'firstnameEN': 'en_firstname',
        'lastnameEN': 'en_lastname',
        'gender': 'gender',
        'idcardnumber': 'pid',
        'passsport_id': 'passport_id',
        'birthday': 'dob',
        'nationality': 'nationality',
        'telephone_number': 'tel',
        'email': 'email',
    }
    UNSUPPORTED_PROFILE_FIELDS = {
        'midnameTH',
        'midnameEN',
        'ethnicity',
        'religion',
    }

    @staticmethod
    def _serialize_legacy_address(address):
        if not address:
            return {}
        return {
            'add_id': address.address_type,
            'add1': address.street_number or '',
            'moo': address.village or '',
            'soi': address.alley or '',
            'road': address.street or '',
            'zipcode': str(address.zipcode) if address.zipcode is not None else '',
            'PROVINCE_NAME': address.province or '',
            'AMPHUR_NAME': address.city or '',
            'DISTRICT_NAME': address.district or '',
            'updt': address.updated_at.isoformat() if address.updated_at else None,
        }

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

        license = member.license
        current_addr = self._serialize_legacy_address(member.mailing_address)
        work_addr = self._serialize_legacy_address(member.working_address)
        home_addr = self._serialize_legacy_address(member.home_address)
        data = {
            'mem_id_txt': member.number,
            'mem_id': member.old_mem_id or member.id,
            'title_id': member.th_title,
            'fname': member.th_firstname,
            'lname': member.th_lastname,
            'e_title': member.en_title,
            'e_fname': member.en_firstname,
            'e_lname': member.en_lastname,
            'birthday': member.dob.isoformat() if member.dob else None,
            'mobilesms': member.tel,
            'email_member': member.email,
            'mem_status': member.status,
            'lic_b_date': license.start_date.isoformat() if license else None,
            'lic_exp_date': license.end_date.isoformat() if license else None,
            'lic_number': license.number if license else None,
            'lic_status_name': license.status if license else None,
            'document_addr': member.mailing_address.address_type if member.mailing_address else '',
            'current_addr': current_addr,
            'home_addr': home_addr,
        }
        data['office'] = {
            'office_position': '',
            'office_name': '',
            'office_department': '',
            'function': '',
            'employer': '',
            'contract': '',
            'office_addr': work_addr,
        }

        cmte_fee_payment_record = license.get_active_cmte_fee_payment() if license else None
        total_score = license.total_cmte_scores if license else 0
        valid_score = license.valid_cmte_scores if license else 0
        data['active_cmte_payment'] = cmte_fee_payment_record.to_dict() if cmte_fee_payment_record else {}
        data['lic_b_date'] = license.start_date.strftime('%Y-%m-%d') if license else None
        data['lic_exp_date'] = license.end_date.strftime('%Y-%m-%d') if license else None

        data['cmte_score'] = {'total': float(total_score), 'valid': float(valid_score)}
        return {'data': data}

    @jwt_required()
    def put(self, pin):
        """
        Update personal information of a member with matching PIN.
        ---
        tags:
            -   Member
        consumes:
            -   application/json
        parameters:
            -   pin: Personal Identification Number
                in: path
                type: string
                required: true
            -   in: body
                required: true
                schema:
                    type: object
                    properties:
                        profile:
                            type: object
        responses:
            200:
                description: Member information updated successfully.
            400:
                description: Invalid request body or field format.
            404:
                description: Member not found.
            409:
                description: Requested PID is already used by another member.
        """
        if not request.is_json:
            return {'message': 'JSON body required.'}, HTTPStatus.BAD_REQUEST

        payload = request.get_json(silent=True) or {}
        profile = payload.get('profile')
        if not isinstance(profile, dict):
            return {'message': 'profile object required.'}, HTTPStatus.BAD_REQUEST

        member = Member.query.filter_by(pid=pin).first()
        if not member:
            return {'message': 'Member not found.'}, HTTPStatus.NOT_FOUND

        updated_fields = []
        ignored_fields = []

        for incoming_field, model_field in self.PROFILE_FIELD_MAP.items():
            if incoming_field not in profile:
                continue

            value = profile.get(incoming_field)
            if isinstance(value, str):
                value = value.strip()
                if value == '':
                    value = None

            if incoming_field == 'birthday':
                if value is None:
                    setattr(member, model_field, None)
                    updated_fields.append(model_field)
                    continue
                try:
                    value = datetime.datetime.strptime(value, '%Y-%m-%d').date()
                except (TypeError, ValueError):
                    return {'message': 'birthday must be in YYYY-MM-DD format.'}, HTTPStatus.BAD_REQUEST

            if incoming_field == 'idcardnumber':
                if not value:
                    return {'message': 'idcardnumber is required.'}, HTTPStatus.BAD_REQUEST
                existing_member = Member.query.filter_by(pid=value).first()
                if existing_member and existing_member.id != member.id:
                    return {'message': 'idcardnumber is already used by another member.'}, HTTPStatus.CONFLICT

            setattr(member, model_field, value)
            updated_fields.append(model_field)

        for field_name in self.UNSUPPORTED_PROFILE_FIELDS:
            if field_name in profile:
                ignored_fields.append(field_name)

        if not updated_fields and not ignored_fields:
            return {'message': 'No supported profile fields provided.'}, HTTPStatus.BAD_REQUEST

        db.session.add(member)
        db.session.commit()

        return {
            'message': 'Member information updated successfully.',
            'data': {
                'pid': member.pid,
                'th_title': member.th_title,
                'th_firstname': member.th_firstname,
                'th_lastname': member.th_lastname,
                'en_title': member.en_title,
                'en_firstname': member.en_firstname,
                'en_lastname': member.en_lastname,
                'gender': member.gender,
                'passport_id': member.passport_id,
                'dob': member.dob.isoformat() if member.dob else None,
                'nationality': member.nationality,
                'tel': member.tel,
                'email': member.email,
            },
            'updated_fields': updated_fields,
            'ignored_fields': ignored_fields,
        }, HTTPStatus.OK


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
