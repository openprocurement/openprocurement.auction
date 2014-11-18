var app = angular.module('app', ['ui.bootstrap', 'pascalprecht.translate', 'timer']);
var db = {};
var bidder_id = "0"

var get_bidder = function getQueryVariable() {
  var query = window.location.search.substring(1);
  var vars = query.split('&');
  for (var i = 0; i < vars.length; i++) {
    var pair = vars[i].split('=');
    if (decodeURIComponent(pair[0]) == 'bidder_id') {
      return decodeURIComponent(pair[1]);
    }
  }
}

app.constant('AuctionConfig', {
  auction_doc_id: auction_doc_id,
  remote_db: db_url
});

app.filter('formatnumber', ['$filter',
  function($filter) {
    return function(val){
      return $filter('number')(val).replace(/,/g, " ")
    }
  }
]);

app.controller('AuctionController', function(
  $scope, AuctionConfig,
  $timeout, $http, $log,
  $rootScope, $location, $translate, $filter
) {
  $scope.format_date = function(date, format) {
    return $filter('date')(date, $filter('translate')(format));
  };
  $scope.bidder_id = get_bidder();
  $scope.lang = 'en';
  $scope.changeLanguage = function(langKey) {
    $translate.use(langKey);
    $scope.lang = langKey;
  };
  $scope.alerts = [];
  $scope.allow_bidding = true;

  $scope.closeAlert = function(msg_id) {
    for (var i = 0; i < $scope.alerts.length; i++) {
      if ($scope.alerts[i].msg_id == msg_id) {
        $scope.alerts.splice(i, 1);
        return true;
      }
    };
  };

  db = $scope.db = new PouchDB(AuctionConfig.remote_db, {
    ajax: {
      cache: true
    }
  });
  $scope.auction_doc = {
    "current_stage": null,

  }
  $scope.auto_close_alert = function(msg_id) {
    $timeout(function() {
      $scope.closeAlert(msg_id)
    }, 400000);
  }
  $scope.setuser = function(bidder_id) {
    $scope.bidder_id = bidder_id;
  }
  $scope.update_countdown_time = function(start_date, end_date) {
    $scope.interval = (end_date - start_date) / 1000;
    if ($scope.interval > 0) {
      $scope.$broadcast('timer-set-countdown', $scope.interval);
      $scope.$broadcast('timer-start');
    };
  }
  $scope.get_round_number = function(pause_index) {
    var pauses = [0];
    if ($scope.auction_doc.stages) {
      $scope.auction_doc.stages.forEach(function(item, index) {
        if (item.type == 'pause') {
          pauses.push(index);
        };
      })
      pauses.push($scope.auction_doc.stages.length - 1);
    }
    if (pause_index <= pauses[0]) {
      return {
        'type': 'pause',
        'data': ['', '1', ]
      }
    }
    for (var i in pauses) {
      if (pause_index < pauses[i]) {
        return {
          'type': 'round',
          'data': parseInt(i) - 1
        }
      } else if ((pause_index == pauses[i]) && (pause_index != $scope.auction_doc.stages.length - 1)) {
        return {
          'type': 'pause',
          'data': [(parseInt(i) - 1).toString(), (parseInt(i)).toString(), ]
        }
      }
    };
    return {
      'type': 'finish'
    }
  }
  $scope.show_bids_form = function(argument) {
    if ((angular.isNumber($scope.auction_doc.current_stage)) && ($scope.auction_doc.current_stage >= 0)) {
      if (($scope.auction_doc.stages[$scope.auction_doc.current_stage].type == 'bids') && ($scope.auction_doc.stages[$scope.auction_doc.current_stage].bidder_id == $scope.bidder_id)) {
        return true;
      } else if (($scope.auction_doc.stages[$scope.auction_doc.current_stage].type == 'preliminary_bids')) {
        for (var i in $scope.auction_doc.initial_bids) {
          if ($scope.auction_doc.initial_bids[i].bidder_id == $scope.bidder_id) {
            return true;
          }
        }
      }
    }
    return false;
  }
  $scope.sync_countdown_time_with_server = function(start) {
    $http.get('/get_current_server_time').success(function(data) {
      $scope.last_sync = new Date(data);
      if (($scope.auction_doc) && ($scope.auction_doc.stages[$scope.auction_doc.current_stage + 1])) {
        var end = new Date($scope.auction_doc.stages[$scope.auction_doc.current_stage + 1]["start"]);
      } else if ($scope.auction_doc) {
        var end = new Date($scope.auction_doc.endDate);
      } else {
        var end = new Date();
      }
      $scope.update_countdown_time($scope.last_sync, end)
    });
  }
  $scope.post_bid = function() {
    if ($scope.BidsForm.$valid) {
      $http.post(AuctionConfig.auction_doc_id + '/postbid', {
        'bid': $scope.bid,
        'bidder_id': $scope.bidder_id || bidder_id || "0"
      }).success(function(data) {
        if (data.status == 'failed') {
          for (var error_id in data.errors) {
            for (var i in data.errors[error_id]) {
              var msg_id = Math.random();
              $scope.alerts.push({
                msg_id: msg_id,
                type: 'danger',
                msg: data.errors[error_id][i]
              });
              $scope.auto_close_alert(msg_id);
            }
          }
        } else {
          var msg_id = Math.random();
          $scope.alerts.push({
            msg_id: msg_id,
            type: 'success',
            msg: 'Bid placed'
          });
          $scope.auto_close_alert(msg_id);
          $scope.allow_bidding = false;
        }

      });
    }
  };
  $scope.edit_bid = function() {
    $scope.allow_bidding = true;
  }
  $scope.get_auction_data = function() {
    db.get(AuctionConfig.auction_doc_id, function(err, doc) {
      $log.debug("Get doc", doc);
      $rootScope.$apply(function(argument) {
        $scope.auction_doc = doc;
      });
    });
  }
  $scope.max_bid_amount = function() {
    if ((angular.isString($scope.bidder_id)) && (angular.isObject($scope.auction_doc))) {
      return $scope.auction_doc.stages[$scope.auction_doc.current_stage].amount - $scope.auction_doc.minimalStep.amount
    }
    return 0
  }
  $scope.calculate_minimal_bid_amount = function() {
    if ((angular.isObject($scope.auction_doc)) && (angular.isArray($scope.auction_doc.stages)) && (angular.isArray($scope.auction_doc.initial_bids))) {
      var bids = [];
      filter_func = function(item, index) {
        if (!angular.isUndefined(item.amount)) {
          bids.push(item.amount);
        };
      }
      $scope.auction_doc.stages.forEach(filter_func);
      $scope.auction_doc.initial_bids.forEach(filter_func);
      $scope.minimal_bid = bids.sort()[0];
    }
  }
  $scope.start_sync = function() {

    $scope.changes = $scope.db.changes({
      live: true,
      style: 'main_only',
      continuous: true,
      include_docs: true,
      since: 0,
      onChange: function(change) {
        $log.debug('onChanges:info - ', change);
        if (change.id == AuctionConfig.auction_doc_id) {
          $scope.replace_document(change.doc);
        }
      }
    });
  };
  $scope.replace_document = function(new_doc) {
    $rootScope.$apply(function(argument) {
      if (($scope.auction_doc.current_stage == null) || (new_doc.current_stage - $scope.auction_doc.current_stage == 0) || (new_doc.current_stage == -1)) {
        $scope.auction_doc = new_doc;
        $scope.sync_countdown_time_with_server();
      } else {
        $scope.bid = null;
        $scope.allow_bidding = true;
        if (new_doc.stages[new_doc.current_stage]["start"]) {
          var start = new Date(new_doc.stages[new_doc.current_stage]["start"]);
        } else {
          var start = new Date();
        }
        if (new_doc.stages[new_doc.current_stage + 1]) {
          var end = new Date(new_doc.stages[new_doc.current_stage + 1]["start"]);
        } else {
          var end = new Date(new_doc.endDate)
        }
        $scope.update_countdown_time(start, end)
        $scope.auction_doc = new_doc;
      }
      $scope.calculate_minimal_bid_amount();
    });
  }
  $scope.db.get(AuctionConfig.auction_doc_id).then(
    function(newdoc) {
      $scope.replace_document(newdoc);
      $scope.sync = $scope.start_sync();
    });

  $scope.restart_changes = function() {
      $scope.replicate.cancel();
      $scope.changes.cancel();
      $scope.start_sync();
    }
    // $scope.get_auction_data();

});