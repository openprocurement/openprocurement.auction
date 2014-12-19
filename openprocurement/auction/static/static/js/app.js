var app = angular.module('auction', ['ui.bootstrap', 'ngCookies', 'pascalprecht.translate', 'timer', 'angular-growl']);
var db = {};
var bidder_id = "0"

app.constant('AuctionConfig', {
  auction_doc_id: auction_doc_id,
  remote_db: db_url,
  restart_retries: 10,
  default_lang: 'uk',
  debug: true
});

app.filter('formatnumber', ['$filter',
  function(filter) {
    return function(val) {
      return filter('number')(val).replace(/,/g, " ")
    }
  }
]);

app.config(['$logProvider', 'AuctionConfig', 'growlProvider', function($logProvider, AuctionConfig, growlProvider) {  
   $logProvider.debugEnabled(AuctionConfig.debug); // default is true
   growlProvider.globalTimeToLive({success: 4000, error: 10000, warning: 10000, info: 4000});
   growlProvider.globalPosition('top-center');
   growlProvider.onlyUniqueMessages(false);
}]);