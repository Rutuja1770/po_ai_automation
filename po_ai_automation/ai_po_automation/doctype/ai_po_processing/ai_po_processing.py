# Copyright (c) 2026, Assimilate and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class AIPOProcessing(Document):
	def validate(self):
		if not self.delivery_date:
			self.delivery_date = frappe.utils.nowdate()

		if (
			self.po_date
			and self.delivery_date
			and frappe.utils.getdate(self.delivery_date)
			< frappe.utils.getdate(self.po_date)
		):
			frappe.msgprint(
				"Delivery Date ({0}) is earlier than PO Date ({1}). "
				"Please change it according to your requirement.".format(
					self.delivery_date, self.po_date
				),
				indicator="orange",
				title="Invalid Delivery Date",
			)
