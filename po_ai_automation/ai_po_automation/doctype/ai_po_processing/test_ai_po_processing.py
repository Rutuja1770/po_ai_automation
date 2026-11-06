# Copyright (c) 2026, Assimilate and Contributors
# See license.txt

from types import SimpleNamespace
from unittest.mock import patch

from frappe.tests import IntegrationTestCase
from po_ai_automation.services.extraction_utils import (
	populate_item_codes_from_descriptions,
)
from po_ai_automation.services.item_service import (
	get_item_master_description,
	get_standard_selling_price,
)
from po_ai_automation.services.sales_order_service import (
	create_sales_order,
	get_taxes_and_charges_rows,
)
from po_ai_automation.services.validation_service import (
	correct_reversed_party_roles,
	validate_po_data,
)


# On IntegrationTestCase, the doctype test records and all
# link-field test record dependencies are recursively loaded
# Use these module variables to add/remove to/from that list
EXTRA_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]
IGNORE_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]



class IntegrationTestAIPOProcessing(IntegrationTestCase):
	"""
	Integration tests for AIPOProcessing.
	Use this class for testing interactions between multiple components.
	"""

	def get_po_data(self, item_code):
		return {
			"customer_name": "Test Customer",
			"supplier_name": "Test Company",
			"po_number": "PO-001",
			"po_date": "2026-01-01",
			"currency": "USD",
			"items": [
				{
					"description": "Description that must not be matched",
					"item_code": item_code,
					"qty": 1,
				}
			],
		}

	def test_extracts_labeled_model_code_from_description(self):
		po_data = {
			"items": [
				{
					"description": (
						"8 CH AI Module, Make- Renu, "
						"Model- FL001A-0800LV3"
					),
					"item_code": None,
				}
			]
		}

		result = populate_item_codes_from_descriptions(po_data)

		self.assertEqual(
			result["items"][0]["item_code"],
			"FL001A-0800LV3",
		)

	def test_extracts_generic_labeled_code_from_description(self):
		po_data = {
			"items": [
				{
					"description": "Code: FP2070TN",
					"item_code": None,
				}
			]
		}

		result = populate_item_codes_from_descriptions(po_data)

		self.assertEqual(
			result["items"][0]["item_code"],
			"FP2070TN",
		)

	def test_extracts_standalone_code_from_product_description(self):
		po_data = {
			"items": [
				{
					"description": "FP4070TN - E",
					"item_code": None,
				},
				{
					"description": "FPEM-0808RP-A0401U-V2",
					"item_code": None,
				},
			]
		}

		result = populate_item_codes_from_descriptions(po_data)

		self.assertEqual(
			[item["item_code"] for item in result["items"]],
			["FP4070TN-E", "FPEM-0808RP-A0401U-V2"],
		)

	def test_does_not_infer_code_from_prose_description(self):
		po_data = {
			"items": [
				{
					"description": "FP4070TN is a module with 8 channels",
					"item_code": None,
				}
			]
		}

		result = populate_item_codes_from_descriptions(po_data)

		self.assertIsNone(result["items"][0]["item_code"])

	def test_uses_explicit_item_code_alias(self):
		po_data = {
			"items": [
				{
					"description": "Unrelated item description",
					"item_code": None,
					"product_code": "ERP-ITEM-1",
				}
			]
		}

		result = populate_item_codes_from_descriptions(po_data)

		self.assertEqual(
			result["items"][0]["item_code"],
			"ERP-ITEM-1",
		)

	def test_does_not_infer_code_from_unlabeled_description(self):
		po_data = {
			"items": [
				{
					"description": "8 CH AI Module FL001A-0800LV3",
					"item_code": None,
				}
			]
		}

		result = populate_item_codes_from_descriptions(po_data)

		self.assertIsNone(result["items"][0]["item_code"])

	def test_preserves_extracted_item_code(self):
		po_data = {
			"items": [
				{
					"description": "Model- FL001A-0800LV3",
					"item_code": "CUSTOMER-CODE",
				}
			]
		}

		result = populate_item_codes_from_descriptions(po_data)

		self.assertEqual(
			result["items"][0]["item_code"],
			"CUSTOMER-CODE",
		)

	@patch(
		"po_ai_automation.services.item_service.frappe.db.get_single_value",
		return_value="Selling",
	)
	@patch(
		"po_ai_automation.services.item_service.frappe.get_all",
		return_value=[SimpleNamespace(name="Selling", currency="USD")],
	)
	def test_selling_price_list_uses_selling_settings(
		self,
		get_all,
		_get_single_value,
	):
		price = get_standard_selling_price(
			"ITEM-1",
			currency="EUR",
		)

		self.assertIsNone(price)
		self.assertEqual(
			get_all.call_args.args[0],
			"Price List",
		)
		self.assertEqual(
			get_all.call_args.kwargs["filters"],
			{
				"name": "Selling",
				"selling": 1,
				"enabled": 1,
			},
		)

	@patch(
		"po_ai_automation.services.item_service.frappe.db.get_value",
		return_value="ERP item master description",
	)
	def test_gets_description_from_matched_item_master(
		self,
		get_value,
	):
		description = get_item_master_description("ITEM-1")

		self.assertEqual(
			description,
			"ERP item master description",
		)
		get_value.assert_called_once_with(
			"Item",
			"ITEM-1",
			"description",
		)

	@patch(
		"po_ai_automation.services.validation_service.find_company_for_po",
		return_value={
			"name": "Matched Company",
			"match_confidence": 100.0,
			"match_method": "gstin",
		},
	)
	@patch(
		"po_ai_automation.services.validation_service.find_customer_for_po",
		return_value={
			"name": "Matched Customer",
			"match_confidence": 100.0,
			"match_method": "gstin",
		},
	)
	@patch(
		"po_ai_automation.services.validation_service.find_item_by_customer_ref",
		return_value=None,
	)
	@patch(
		"po_ai_automation.services.validation_service.find_item_by_code",
		return_value={
			"name": "ERP-ITEM-1",
			"match_confidence": 95.0,
		},
	)
	def test_customer_and_company_gstin_are_fallbacks(
		self,
		_find_item_by_code,
		_find_item_by_customer_ref,
		_find_customer_for_po,
		_find_company_for_po,
	):
		po_data = self.get_po_data("ERP-ITEM-1")
		po_data.update({
			"customer_name": "Unmatched Customer Name",
			"customer_gstin": "27ABCDE1234F1Z5",
			"supplier_name": "Unmatched Supplier Name",
			"supplier_gstin": "29ABCDE1234F1Z8",
		})

		result = validate_po_data(po_data)

		self.assertTrue(result["valid"])
		self.assertEqual(result["customer"], "Matched Customer")

	def test_customer_name_is_used_when_gstin_does_not_match(self):
		from po_ai_automation.services import customer_service

		with patch.object(
			customer_service,
			"find_customer_by_gstin",
			return_value=None,
		) as find_by_gstin, patch.object(
			customer_service,
			"find_customer_with_confidence",
			return_value={"name": "Name Match"},
		) as find_by_name:
			result = customer_service.find_customer_for_po(
				"Ryali Technologies",
				"UNMATCHED-GSTIN",
			)

		self.assertEqual(result["name"], "Name Match")
		find_by_gstin.assert_called_once_with("UNMATCHED-GSTIN")
		find_by_name.assert_called_once_with("Ryali Technologies")

	def test_customer_name_is_used_when_gstin_is_missing(self):
		from po_ai_automation.services import customer_service

		with patch.object(
			customer_service,
			"find_customer_with_confidence",
			return_value={"name": "Name Match"},
		) as find_by_name:
			result = customer_service.find_customer_for_po(
				"Customer Name",
				None,
			)

		self.assertEqual(result["name"], "Name Match")
		find_by_name.assert_called_once_with("Customer Name")

	def test_company_name_is_used_when_gstin_does_not_match(self):
		from po_ai_automation.services import company_service

		with patch.object(
			company_service,
			"find_company_by_gstin",
			return_value=None,
		) as find_by_gstin, patch.object(
			company_service,
			"find_matching_company",
			return_value={"name": "Name Match"},
		) as find_by_name:
			result = company_service.find_company_for_po(
				"Supplier Name",
				"UNMATCHED-GSTIN",
			)

		self.assertEqual(result["name"], "Name Match")
		find_by_gstin.assert_called_once_with("UNMATCHED-GSTIN")
		find_by_name.assert_called_once_with("Supplier Name")

	def test_company_name_is_used_when_gstin_is_missing(self):
		from po_ai_automation.services import company_service

		with patch.object(
			company_service,
			"find_matching_company",
			return_value={"name": "Name Match"},
		) as find_by_name:
			result = company_service.find_company_for_po(
				"Supplier Name",
				None,
			)

		self.assertEqual(result["name"], "Name Match")
		find_by_name.assert_called_once_with("Supplier Name")

	def test_company_name_match_ignores_pvt_ltd_punctuation(self):
		from po_ai_automation.services import company_service

		with patch.object(
			company_service.frappe.db,
			"get_value",
			return_value=None,
		), patch.object(
			company_service.frappe.db,
			"exists",
			return_value=None,
		), patch.object(
			company_service.frappe,
			"get_all",
			side_effect=[
				[],
				[
					SimpleNamespace(
						name="RENU FACTORY AUTOMATION PRIVATE LIMITED",
						company_name=(
							"Renu Factory Automation Private Limited"
						),
					)
				],
			],
		) as get_all:
			result = company_service.find_matching_company(
				"RENU FACTORY AUTOMATION PVT.LTD."
			)

		self.assertEqual(
			result["name"],
			"RENU FACTORY AUTOMATION PRIVATE LIMITED",
		)
		self.assertEqual(get_all.call_count, 2)

	def test_duplicate_identical_igst_rows_are_removed(self):
		rows = [
			{
				"account_head": "Output Tax IGST - RENU",
				"charge_type": "On Net Total",
				"rate": 18,
				"row_id": None,
			},
			{
				"account_head": "Output Tax IGST - RENU",
				"charge_type": "On Net Total",
				"rate": 18,
				"row_id": None,
			},
			{
				"account_head": "Output Tax IGST - RENU",
				"charge_type": "On Net Total",
				"rate": 9,
				"row_id": None,
			},
			{
				"account_head": "Freight Charges - RENU",
				"charge_type": "On Net Total",
				"rate": 0,
				"row_id": None,
			},
		]

		with patch(
			"erpnext.controllers.accounts_controller.get_taxes_and_charges",
			return_value=rows,
		):
			result = get_taxes_and_charges_rows("Output GST Out-state")

		self.assertEqual(len(result), 3)
		self.assertEqual(
			[row["rate"] for row in result],
			[18, 9, 0],
		)
		self.assertEqual(
			result[1]["account_head"],
			"Freight Charges - RENU",
		)

	@patch(
		"po_ai_automation.services.validation_service.find_company_for_po",
		side_effect=lambda name, gstin: (
			{"name": "RENU", "match_confidence": 100.0}
			if gstin == "RENU-GSTIN"
			else None
		),
	)
	@patch(
		"po_ai_automation.services.validation_service.find_customer_for_po",
		side_effect=lambda name, gstin: (
			{"name": "HBS", "match_confidence": 100.0}
			if gstin == "HBS-GSTIN"
			else None
		),
	)
	def test_corrects_reversed_parties_using_master_matches(
		self,
		_find_customer,
		_find_company,
	):
		po_data = {
			"customer_name": "Renu Factory Automation Private Limited",
			"customer_gstin": "RENU-GSTIN",
			"supplier_name": "HBS Automation Systems",
			"supplier_gstin": "HBS-GSTIN",
		}

		result = correct_reversed_party_roles(po_data)

		self.assertEqual(
			result["customer_name"],
			"HBS Automation Systems",
		)
		self.assertEqual(result["customer_gstin"], "HBS-GSTIN")
		self.assertEqual(
			result["supplier_name"],
			"Renu Factory Automation Private Limited",
		)
		self.assertEqual(result["supplier_gstin"], "RENU-GSTIN")

	@patch(
		"po_ai_automation.services.validation_service.find_company_by_gstin",
		side_effect=lambda gstin: (
			{"name": "RENU", "match_confidence": 100.0}
			if gstin == "RENU-GSTIN"
			else None
		),
	)
	@patch(
		"po_ai_automation.services.validation_service.find_customer_for_po",
		side_effect=lambda name, gstin: (
			{"name": "HBS", "match_confidence": 100.0}
			if name == "HBS Automation Systems"
			else None
		),
	)
	def test_company_gstin_identifies_supplier_before_role_fallbacks(
		self,
		_find_customer,
		_find_company,
	):
		po_data = {
			"customer_name": "Renu Factory Automation Private Limited",
			"customer_gstin": "RENU-GSTIN",
			"supplier_name": "HBS Automation Systems",
			"supplier_gstin": None,
		}

		result = correct_reversed_party_roles(po_data)

		self.assertEqual(
			result["customer_name"],
			"HBS Automation Systems",
		)
		self.assertIsNone(result["customer_gstin"])
		self.assertEqual(
			result["supplier_name"],
			"Renu Factory Automation Private Limited",
		)
		self.assertEqual(result["supplier_gstin"], "RENU-GSTIN")

	@patch(
		"po_ai_automation.services.sales_order_service.get_default_address",
		return_value="Company-Address-1",
	)
	@patch(
		"po_ai_automation.services.sales_order_service.frappe.new_doc",
	)
	def test_sales_order_uses_default_company_address(
		self,
		new_doc,
		get_default_address,
	):
		sales_order = SimpleNamespace(
			customer=None,
			company=None,
			company_address=None,
			items=[],
			taxes=[],
			append=lambda table, row: SimpleNamespace(),
			extend=lambda table, rows: None,
			insert=lambda **kwargs: None,
			get=lambda fieldname: getattr(sales_order, fieldname),
		)
		new_doc.return_value = sales_order
		with patch(
			"po_ai_automation.services.sales_order_service.get_taxes_and_charges_template",
			return_value=None,
		), patch(
			"po_ai_automation.services.sales_order_service.get_source_warehouse",
			return_value="Warehouse-1",
		), patch(
			"po_ai_automation.services.sales_order_service.frappe.get_cached_value",
			return_value=0,
		):
			create_sales_order(
				{},
				{
					"valid": True,
					"customer": "Customer-1",
					"company": "Company-1",
					"items": [
						{
							"erpnext_item": "Item-1",
							"qty": 1,
							"rate": 10,
						}
					],
				},
			)

		self.assertEqual(
			sales_order.company_address,
			"Company-Address-1",
		)
		get_default_address.assert_called_once_with(
			"Company",
			"Company-1",
		)

	@patch(
		"po_ai_automation.services.validation_service.find_matching_company",
		return_value={"name": "Test Company", "match_confidence": 100.0},
	)
	@patch(
		"po_ai_automation.services.validation_service.find_customer_with_confidence",
		return_value={"name": "Test Customer", "match_confidence": 100.0},
	)
	@patch(
		"po_ai_automation.services.validation_service.find_item_by_customer_ref"
	)
	@patch(
		"po_ai_automation.services.validation_service.find_item_by_code"
	)
	def test_item_code_match_does_not_use_description(
		self,
		find_item_by_code,
		find_item_by_customer_ref,
		_find_customer,
		_find_company,
	):
		find_item_by_code.return_value = {
			"name": "ERP-ITEM-1",
			"match_confidence": 95.0,
		}

		result = validate_po_data(
			self.get_po_data("ERP-ITEM-1")
		)

		self.assertTrue(result["valid"])
		self.assertEqual(
			result["items"][0]["erpnext_item"],
			"ERP-ITEM-1",
		)
		find_item_by_customer_ref.assert_not_called()

	@patch(
		"po_ai_automation.services.validation_service.find_matching_company",
		return_value={"name": "Test Company", "match_confidence": 100.0},
	)
	@patch(
		"po_ai_automation.services.validation_service.find_customer_with_confidence",
		return_value={"name": "Test Customer", "match_confidence": 100.0},
	)
	@patch(
		"po_ai_automation.services.validation_service.find_item_by_code",
		return_value=None,
	)
	@patch(
		"po_ai_automation.services.validation_service.find_item_by_customer_ref",
		return_value={"name": "ERP-ITEM-2", "match_confidence": 85.0},
	)
	def test_customer_reference_is_used_when_item_code_does_not_match(
		self,
		find_item_by_customer_ref,
		_find_item_by_code,
		_find_customer,
		_find_company,
	):
		result = validate_po_data(
			self.get_po_data("CUSTOMER-REF-2")
		)

		self.assertTrue(result["valid"])
		self.assertEqual(
			result["items"][0]["erpnext_item"],
			"ERP-ITEM-2",
		)
		find_item_by_customer_ref.assert_called_once_with(
			"CUSTOMER-REF-2",
			"Test Customer",
		)

	@patch(
		"po_ai_automation.services.validation_service.find_matching_company",
		return_value={"name": "Test Company", "match_confidence": 100.0},
	)
	@patch(
		"po_ai_automation.services.validation_service.find_customer_with_confidence",
		return_value={"name": "Test Customer", "match_confidence": 100.0},
	)
	@patch(
		"po_ai_automation.services.validation_service.find_item_by_code",
		return_value=None,
	)
	@patch(
		"po_ai_automation.services.validation_service.find_item_by_customer_ref",
		return_value=None,
	)
	def test_description_alone_does_not_match_item(
		self,
		_find_item_by_customer_ref,
		_find_item_by_code,
		_find_customer,
		_find_company,
	):
		result = validate_po_data(
			self.get_po_data(None)
		)

		self.assertFalse(result["valid"])
		self.assertEqual(
			result["items"][0]["validation_status"],
			"Failed",
		)
