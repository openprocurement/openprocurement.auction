var app = angular.module('auction', ['ui.bootstrap', 'pascalprecht.translate', 'timer']);
var db = {};
var bidder_id = "0"

app.constant('AuctionConfig', {
  auction_doc_id: auction_doc_id,
  remote_db: db_url,
  restart_retries: 10,
  default_lang: 'uk'
});

app.filter('formatnumber', ['$filter',
  function(filter) {
    return function(val) {
      return filter('number')(val).replace(/,/g, " ")
    }
  }
]);