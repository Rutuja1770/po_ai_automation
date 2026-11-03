# Copyright (c) 2026, Assimilate and Contributors
# See license.txt

from types import SimpleNamespace
from unittest.mock import patch

from frappe.tests import IntegrationTestCase
from po_ai_automation.services.extraction_utils import (
	populate_item_codes_from_descriptions,
)
from po_ai_automation.services.item_service import (
	get_standard_selling_price,
)
from po_ai_automation.services.sales_order_service import (
	create_sales_order,
)
from po_ai_automation.services.validation_service import validate_po_data


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
		"po_ai_automation.services.validation_service.find_matching_company",
		return_value=None,
	)
	@patch(
		"po_ai_automation.services.validation_service.find_company_by_gstin",
		return_value={
			"name": "Matched Company",
			"match_confidence": 100.0,
			"match_method": "gstin",
		},
	)
	@patch(
		"po_ai_automation.services.validation_service.find_customer_with_confidence",
		return_value=None,
	)
	@patch(
		"po_ai_automation.services.validation_service.find_customer_by_gstin",
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
		find_customer_by_gstin,
		_find_customer_by_name,
		find_company_by_gstin,
		_find_company_by_name,
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
		self.assertEqual(result["company"], "Matched Company")
		find_customer_by_gstin.assert_called_once_with("27ABCDE1234F1Z5")
		find_company_by_gstin.assert_called_once_with("29ABCDE1234F1Z8")

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
