var auction_doc_id = 'test';

beforeEach(function() {
    module('auction')
    timerCallback = jasmine.createSpy("timerCallback");
    jasmine.clock().install();
  });

afterEach(function() {
    jasmine.clock().uninstall();
  });

angular.mock.module('AuctionUtils');

describe('Unit: Testing AuctionUtils "pad" ', function() {
  it('should be Defined', angular.mock.inject(['AuctionUtils', function(AuctionUtils) {
    expect(AuctionUtils.pad).toBeDefined();
  }]));

  it('should be convert 10 to "10"', angular.mock.inject(['AuctionUtils', function(AuctionUtils) {
    expect(AuctionUtils.pad(10)).toEqual("10");
  }]));

  it('should be convert 1 to "01"', angular.mock.inject(['AuctionUtils', function(AuctionUtils) {
    expect(AuctionUtils.pad(1)).toEqual("01");
  }]));
});


describe('Unit: Testing AuctionUtils "prepare_info_timer_data" ', function() {
  it('should be Defined', angular.mock.inject(['AuctionUtils', function(AuctionUtils) {
    expect(AuctionUtils.prepare_info_timer_data).toBeDefined();
  }]));

  it('should inform about tender cancalled', angular.mock.inject(['AuctionUtils', function(AuctionUtils) {
    expect(AuctionUtils.prepare_info_timer_data(current_time, auction, bidder_id, Rounds)).toEqual({
      countdown: false,
      start_time: true,
      msg: 'Tender cancelled'
    });
  }]));

  it('should inform about tender rescheduled', angular.mock.inject(['AuctionUtils', function(AuctionUtils) {
    auction.current_stage = -101;
    expect(AuctionUtils.prepare_info_timer_data(current_time, auction, bidder_id, Rounds)).toEqual({
      countdown: false,
      start_time: true,
      msg: 'Auction has not started and will be rescheduled'
    });
  }]));

  it('should inform about expectations start of the auction', angular.mock.inject(['AuctionUtils', function(AuctionUtils) {
    auction.current_stage = -1;
    auction.stages[0].start = 
    expect(AuctionUtils.prepare_info_timer_data(current_time, auction, bidder_id, Rounds)).toEqual({
      countdown: true,
      start_time: false,
      msg: 'Waiting'
    });
  }]));
});