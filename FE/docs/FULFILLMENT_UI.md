# Shipping and workshop collection UI

Frontend integration only. No backend implementation or business rules were changed.

## Where to find it

- Staff and Manager rail: **Shipping and collection**, `/staff/fulfillment`.
- An order: `/staff/fulfillment/:orderId`, or the fulfillment section in `/staff/review/:orderId`.
- Queue tabs: ready for handover, delivering, awaiting final payment, completed, all fulfillment orders.
- Search, order type and server pagination remain available. Staff see their authorized orders; Managers can view all authorized workshop orders.
- Managers can assign/reassign active orders using the existing manager assignment API. They do not get shipment or pickup mutation controls.

## Delivery

The **Shipping and collection** section can be expanded or collapsed (initially open). Its **Waybill history** starts collapsed and shows the number of waybills; expand it to see records, newest first. Collapsing either section keeps the forms mounted and preserves unsent input. Both disclosures work in order details and the fulfillment desk, including Manager read-only views.

The mock carrier test form keeps its original permissions, confirmation checkbox and validation. Its legend sits inside the warning card, and the warning text and fields wrap on small screens.

1. Customer chooses a service and pays the final balance plus shipping. Backend moves the order to `READY_TO_DELIVER`.
2. Assigned Staff verify recipient/contact/address, paid amounts, the saved carrier/service and packing.
3. Staff create a waybill with an optional note, at most 300 characters. Package dimensions/weight and carrier selection are calculated by the backend, not invented by the UI.
4. Staff can open the label, refresh its temporary link, and open the carrier tracking page when the API supplies links. If no label exists, use the carrier's own tools with the waybill code.
5. Creating a waybill leaves the order ready for handover. Only the carrier pickup/in-transit callback moves it to `DELIVERING`. A delivered callback moves it to `COMPLETED`.
6. Staff can cancel a `CREATED` waybill with a required reason. This cancels the waybill only, not the order or payments. No cancellation control is shown after pickup.
7. Failed/returned shipments show an unresolved-delivery warning. Staff can create a replacement if the latest waybill is no longer active. History retains every returned/cancelled/replaced waybill.

Mock shipments expose an explicitly labeled test form. It sends only transitions supported by the existing carrier state machine. The operator must acknowledge that it changes saved order data. Real/sandbox shipments do not get these controls. Test failure/return requires an explanatory note.

## Workshop collection

1. Customer saves a collection slot/contact phone and completes final payment.
2. Assigned Staff see recipient, contact, workshop address and appointment in Vietnam time.
3. At collection, Staff enter the presented order code and phone, and acknowledge physically handing over the product.
4. The backend verifies the phone and completes the order. A mismatch keeps the form available with translated feedback; the order is refreshed after success or failure.

## Customer follow-up

The order review page shows the saved receiving information, collection appointment or waybill history and carrier links. It polls shipment updates while the order is active. A customer may explicitly record physical receipt when the backend permits it. Receipt confirmation records `received_confirmed_at`; it does not itself complete the order.

## Existing API limitations

- The delivery-choice endpoint only accepts changes before final payment. There is no supported frontend action to switch a paid delivery order to workshop collection. Failed/returned shipments explain this limitation rather than offering a broken action.
- Shipment reads expose current status, raw carrier code and pickup/delivery timestamps, not a complete carrier-event log or persisted failure reason. The UI shows only available information.
- Shipment fees are the amount the customer paid, which may be a fallback fee. The actual amount billed by the carrier is not exposed in shipment reads.
- Pickup confirmation accepts the order ID and phone. Entering the visible order code is an additional UI verification, not a new backend parameter.
- Refunds and manual payment approval are not part of these endpoints. Successful final payment is still confirmed by the existing payment backend.

## Validation

```powershell
npm.cmd run build
npm.cmd run i18n:check
node scripts/check-fulfillment-browser.mjs
node scripts/check-final-payment-browser.mjs
```

Browser tests use an isolated Edge profile and intercept all external/API requests with local fixtures. They verify create/label/cancel/replacement, failed and returned delivery, carrier pickup/completion, real shipment control restrictions, unpaid orders, read-error duplicate protection, Manager read-only access, phone mismatch/correct pickup, customer tracking/receipt, Vietnamese/Japanese and mobile layout. They do not validate deployed carrier credentials, real callbacks, database migrations or physical shipment fulfillment.
