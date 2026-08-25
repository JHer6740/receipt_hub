// One money formatter for the whole app.
//
// There used to be two: `formatCents` in the design layer (intl, grouped
// thousands) and `money` in the pricing engine (hand-built, ungrouped). Both
// rendered on the same comparison card, so above $1,000 the same amount
// appeared as `$1,234.56` in one row and `$1234.56` in the next.
//
// Currency is fixed to en_AU for the launch market. Anything that needs a
// second currency changes it here, in one place.

import 'package:intl/intl.dart';

final NumberFormat _currency = NumberFormat.currency(
  locale: 'en_AU',
  symbol: r'$',
);

/// Format integer cents as money.
String formatCents(num cents) => _currency.format(cents / 100);
